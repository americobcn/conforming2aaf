from fractions import Fraction as F

from conform2aaf.readers.xmeml import read_xmeml

XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
 <sequence id="seq-1">
  <name>Reel 1</name>
  <rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
  <timecode><rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate>
   <string>01:00:00:00</string><frame>86400</frame><displayformat>NDF</displayformat></timecode>
  <media><audio>
   <track>
    <clipitem id="c1">
     <name>12A_T3</name><start>0</start><end>-1</end><in>48</in><out>108</out>
     <file id="file-1"><name>12A_T3.wav</name>
      <pathurl>file://localhost/Volumes/Sound/Day%201/12A_T3.wav</pathurl>
      <timecode><rate><timebase>24</timebase><ntsc>TRUE</ntsc></rate><frame>864000</frame></timecode>
     </file>
     <sourcetrack><mediatype>audio</mediatype><trackindex>2</trackindex></sourcetrack>
     <filter><effect><effectid>audiolevels</effectid>
      <parameter><parameterid>level</parameterid><value>0.5</value></parameter></effect></filter>
    </clipitem>
    <transitionitem><start>40</start><end>52</end><alignment>center</alignment></transitionitem>
    <clipitem id="c2">
     <name>12A_T4</name><start>-1</start><end>100</end><in>0</in><out>60</out>
     <file id="file-1"/>
     <sourcetrack><mediatype>audio</mediatype><trackindex>2</trackindex></sourcetrack>
    </clipitem>
    <transitionitem><start>94</start><end>100</end><alignment>end-black</alignment></transitionitem>
   </track>
   <track premiereTrackType="Stereo">
    <clipitem id="c3"><name>music</name><start>0</start><end>24</end><in>0</in><out>24</out>
     <file id="file-2"><name>music.wav</name></file></clipitem>
   </track>
   <track><enabled>FALSE</enabled></track>
  </audio></media>
 </sequence>
</xmeml>
"""


def test_reads_xmeml(tmp_path):
    p = tmp_path / "r1.xml"
    p.write_text(XML)
    tl = read_xmeml(p)
    fps = F(24000, 1001)
    assert tl.name == "Reel 1" and tl.rate.fps == fps and not tl.rate.drop
    assert tl.start == 86400 / fps
    assert [t.name for t in tl.tracks] == ["A1", "A2.L", "A2.R"]

    a, b = tl.tracks[0].clips
    assert a.record_in == tl.start and a.duration == 46 / fps  # cut at centre of 40..52
    assert a.source_in == 864000 / fps + 48 / fps
    assert a.file_hint == "/Volumes/Sound/Day 1/12A_T3.wav"
    assert a.channel == 2 and round(a.gain_db, 2) == -6.02

    assert b.record_in == tl.start + 46 / fps and b.duration == 54 / fps
    assert b.crossfade_in == 12 / fps and b.crossfade_pre == 6 / fps
    assert b.source_in == 864000 / fps + 6 / fps
    assert b.fade_out == 6 / fps

    l, r = tl.tracks[1].clips[0], tl.tracks[2].clips[0]
    assert (l.channel, r.channel) == (1, 2) and l.source_in is None and l.file_hint == "music.wav"
    assert any("desactivada" in w for w in tl.warnings)


PIC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
 <sequence id="seq-1">
  <name>Pic</name>
  <rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate>
  <timecode><rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate>
   <string>01:00:00:00</string><frame>90000</frame><displayformat>NDF</displayformat></timecode>
  <media>
   <video><track>
    <clipitem id="v1">
     <name>A001C002</name><start>0</start><end>50</end><in>25</in><out>75</out>
     <logginginfo><scene>5 12</scene><shottake>3</shottake></logginginfo>
     <file id="f1"><name>A001C002.mov</name>
      <pathurl>file://localhost/Volumes/Cam/A001C002.mov</pathurl>
      <timecode><rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate>
       <string>10:00:00:00</string><frame>900000</frame><displayformat>NDF</displayformat>
       <reel><name>A001</name></reel></timecode>
     </file>
    </clipitem>
    <clipitem id="v2"><name>A001C003</name><start>50</start><end>100</end><in>0</in><out>50</out>
     <enabled>FALSE</enabled><file id="f1"/></clipitem>
    <clipitem id="v3"><name>A001C004</name><start>100</start><end>150</end><in>50</in><out>100</out><file id="f1"/></clipitem>
   </track></video>
   <audio><track>
    <clipitem id="a1"><name>camera audio</name><start>0</start><end>50</end><in>0</in><out>50</out><file id="f1"/>
     <sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack></clipitem>
   </track></audio>
  </media>
 </sequence>
</xmeml>
"""


def test_picture_mode_reads_video_clips_with_metadata(tmp_path):
    p = tmp_path / "pic.xml"
    p.write_text(PIC_XML)
    tl = read_xmeml(p, picture=True)
    assert tl.picture and [t.name for t in tl.tracks] == ["V1"]
    a, b = tl.tracks[0].clips  # the disabled clip is skipped
    assert (a.name, a.channel, a.reel, a.scene, a.take) == ("A001C002", None, "A001", "5 12", "3")
    assert a.record_in == F(3600) and a.duration == F(2) and a.source_in == F(36001)
    assert a.file_hint == "/Volumes/Cam/A001C002.mov"
    assert b.name == "A001C004" and b.record_in == F(3604) and b.source_in == F(36002)
    assert any("desactivado" in w for w in tl.warnings)


def test_audio_mode_still_reads_audio_tracks(tmp_path):
    p = tmp_path / "pic.xml"
    p.write_text(PIC_XML)
    tl = read_xmeml(p)
    assert not tl.picture and [c.name for c in tl.clips()] == ["camera audio"]


# Premiere "synced" clips: each cut is a nested sequence holding the camera clip and the production WAV.
NESTED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
 <sequence id="sequence-1">
  <name>Nested</name>
  <rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate>
  <timecode><rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate>
   <string>00:00:00:00</string><frame>0</frame><displayformat>NDF</displayformat></timecode>
  <media>
   <video>
    <track>
     <clipitem id="t1"><name>A003C007_261009_RNU8.mov</name><start>25</start><end>50</end><in>10</in><out>35</out>
      <sequence id="sequence-3">
       <name>A003C007_261009_RNU8.mov</name>
       <media><video><track>
        <clipitem id="n5"><name>A003C007_261009_RNU8.mov</name><start>0</start><end>100</end><in>0</in><out>100</out>
         <file id="file-cam2"><name>A003C007_261009_RNU8.mov</name>
          <timecode><rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate><string>11:00:00:00</string></timecode></file>
        </clipitem></track></video>
        <audio><track>
         <clipitem id="n6"><name>A003C007_261009_RNU8.mov</name><start>0</start><end>100</end><in>0</in><out>100</out>
          <file id="file-cam2"/></clipitem></track></audio></media>
      </sequence>
     </clipitem>
    </track>
    <track><clipitem id="t0"><name>Logo.png</name><start>60</start><end>70</end><in>0</in><out>10</out>
     <file id="file-png"><name>Logo.png</name></file></clipitem></track>
   </video>
   <audio>
    <track premiereTrackType="Stereo">
     <clipitem id="a1"><name>A_0001C004_261028_092634_h1DPY.mp4</name><start>0</start><end>25</end><in>50</in><out>75</out>
      <sequence id="sequence-2">
       <name>A_0001C004_261028_092634_h1DPY.mp4</name>
       <media>
        <video><track>
         <clipitem id="n1"><name>A_0001C004_261028_092634_h1DPY.mp4</name><start>10</start><end>200</end><in>0</in><out>190</out>
          <file id="file-cam"><name>A_0001C004_261028_092634_h1DPY.mp4</name>
           <pathurl>file://localhost/Volumes/Cam/A_0001C004_261028_092634_h1DPY.mp4</pathurl>
           <timecode><rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate><string>10:00:00:00</string></timecode></file>
         </clipitem></track></video>
        <audio>
         <track><clipitem id="n2"><name>01-01T04.WAV</name><start>0</start><end>200</end><in>0</in><out>200</out>
          <file id="file-wav"><name>01-01T04.WAV</name>
           <pathurl>file://localhost/Volumes/Snd/26Y10M28/01-01T04.WAV</pathurl>
           <timecode><rate><timebase>25</timebase><ntsc>FALSE</ntsc></rate><string>09:59:59:15</string>
            <reel><name>26Y10M28</name></reel></timecode></file>
          <sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack></clipitem></track>
         <track><clipitem id="n3"><name>01-01T04.WAV</name><start>0</start><end>200</end><in>0</in><out>200</out>
          <file id="file-wav"/><sourcetrack><mediatype>audio</mediatype><trackindex>2</trackindex></sourcetrack></clipitem></track>
         <track><clipitem id="n4"><name>A_0001C004_261028_092634_h1DPY.mp4</name><start>10</start><end>200</end><in>0</in><out>190</out>
          <file id="file-cam"/></clipitem></track>
        </audio>
       </media>
      </sequence>
     </clipitem>
     <clipitem id="a2"><name>A_0001C004_261028_092634_h1DPY.mp4</name><start>50</start><end>75</end><in>0</in><out>25</out>
      <enabled>FALSE</enabled><sequence id="sequence-2"/></clipitem>
    </track>
    <track premiereTrackType="Stereo">
     <clipitem id="a3"><name>A_0001C004_261028_092634_h1DPY.mp4</name><start>0</start><end>25</end><in>50</in><out>75</out>
      <sequence id="sequence-2"/></clipitem>
     <clipitem id="a4"><name>music.wav</name><start>0</start><end>100</end><in>0</in><out>100</out>
      <file id="file-music"><name>music.wav</name></file></clipitem>
    </track>
   </audio>
  </media>
 </sequence>
</xmeml>
"""


def test_picture_mode_takes_cuts_from_nested_sequences(tmp_path):
    p = tmp_path / "nested.xml"
    p.write_text(NESTED_XML)
    tl = read_xmeml(p, picture=True)
    assert tl.picture
    cuts = {c.name: c for c in tl.clips()}
    # the nested clip used on two audio tracks is one cut; the disabled one and the music are left out
    assert sorted(cuts) == ["A003C007_261009_RNU8.mov", "A_0001C004_261028_092634_h1DPY.mp4", "Logo.png"]

    snd = cuts["A_0001C004_261028_092634_h1DPY.mp4"]
    assert snd.record_in == 0 and snd.duration == 1
    # WAV TC 09:59:59:15 + 50 frames into the nested sequence = 10:00:01:15
    assert snd.source_in == F(36001) + F(15, 25)
    assert snd.file_hint == "/Volumes/Snd/26Y10M28/01-01T04.WAV" and snd.reel == "26Y10M28"
    assert snd.channel is None

    # no WAV in the nested sequence: the camera TC is used (11:00:00:00 + 10 frames)
    cam = cuts["A003C007_261009_RNU8.mov"]
    assert cam.record_in == 1 and cam.duration == 1 and cam.source_in == F(39600) + F(10, 25)
    assert any("desactivado" in w for w in tl.warnings)


def test_nested_cut_is_split_where_the_wav_ends(tmp_path):
    xml = NESTED_XML.replace("<start>0</start><end>200</end><in>0</in><out>200</out>\n          <file id=\"file-wav\"><name>",
                             "<start>0</start><end>60</end><in>0</in><out>60</out>\n          <file id=\"file-wav\"><name>")
    xml = xml.replace('<clipitem id="n3"><name>01-01T04.WAV</name><start>0</start><end>200</end><in>0</in><out>200</out>',
                      '<clipitem id="n3"><name>01-01T04.WAV</name><start>0</start><end>60</end><in>0</in><out>60</out>')
    p = tmp_path / "nested.xml"
    p.write_text(xml)
    tl = read_xmeml(p, picture=True)
    parts = sorted((c for c in tl.clips() if c.name.startswith("A_0001")), key=lambda c: c.record_in)
    # frames 50..60 come from the WAV, 60..75 only have the camera clip
    assert [(c.record_in, c.duration) for c in parts] == [(0, F(10, 25)), (F(10, 25), F(15, 25))]
    assert parts[0].file_hint.endswith("01-01T04.WAV")
    assert parts[1].file_hint.endswith(".mp4") and parts[1].source_in == F(36000) + F(50, 25)
