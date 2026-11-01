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
