from fractions import Fraction as F

import pytest

from conform2aaf.readers.fcpxml import read_fcpxml

FCPXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
 <resources>
  <format id="r1" frameDuration="1001/24000s"/>
  <asset id="r2" name="12A_T3" start="36000s" duration="60s" hasAudio="1" audioChannels="2">
   <media-rep kind="original-media" src="file:///Volumes/Sound/Day%201/12A_T3.wav"/>
  </asset>
  <asset id="r3" name="music" start="0s" duration="100s" hasAudio="1" audioChannels="1">
   <media-rep kind="original-media" src="file:///Volumes/Music/music.wav"/>
  </asset>
  <media id="r4" name="Compound"><sequence format="r1"><spine>
   <asset-clip ref="r3" offset="0s" start="10s" duration="20s" audioRole="music"/>
  </spine></sequence></media>
  <media id="r5" name="MC"><multicam format="r1">
   <mc-angle name="Cam" angleID="a1"><asset-clip ref="r3" offset="0s" duration="100s" audioRole="music"/></mc-angle>
   <mc-angle name="Sound" angleID="a2"><asset-clip ref="r2" offset="0s" start="36000s" duration="60s"/></mc-angle>
  </multicam></media>
 </resources>
 <library><event name="E"><project name="P1">
  <sequence format="r1" tcStart="3600s" tcFormat="NDF"><spine>
   <asset-clip ref="r2" offset="3600s" start="36002s" duration="5s" name="12A_T3" audioRole="dialogue.boom">
    <adjust-volume amount="-6dB"/>
    <asset-clip ref="r3" lane="-1" offset="36003s" start="0s" duration="2s" audioRole="music"/>
    <asset-clip ref="r3" lane="-2" offset="72007/2s" start="0s" duration="2s" audioRole="music"/>
   </asset-clip>
   <transition offset="3604s" duration="2s" name="Cross Dissolve"/>
   <asset-clip ref="r2" offset="3605s" start="36010s" duration="5s" name="12A_T3b" audioRole="dialogue.boom">
    <audio-channel-source srcCh="1" role="dialogue.boom"/>
    <audio-channel-source srcCh="2" role="dialogue.lav" enabled="0"/>
   </asset-clip>
   <ref-clip ref="r4" offset="3610s" start="15s" duration="5s" name="Compound"/>
   <mc-clip ref="r5" offset="3615s" start="20s" duration="2s" name="MC">
    <mc-source angleID="a1" srcEnable="video"/>
    <mc-source angleID="a2" srcEnable="audio"/>
   </mc-clip>
   <gap offset="3617s" start="3600s" duration="1s" name="Gap"/>
  </spine></sequence>
 </project></event></library>
</fcpxml>
"""


@pytest.fixture
def tl(tmp_path):
    p = tmp_path / "p.fcpxml"
    p.write_text(FCPXML)
    return read_fcpxml(p)


def test_header(tl):
    assert tl.name == "P1" and tl.rate.fps == F(24000, 1001) and tl.start == 3600


def test_tracks_by_role_channel_and_overlap(tl):
    assert [t.name for t in tl.tracks] == [
        "dialogue.boom 1", "dialogue.boom 2", "music", "music #2", "dialogue 1", "dialogue 2",
    ]


def test_primary_clip_and_transition(tl):
    a, b = tl.tracks[0].clips
    assert (a.record_in, a.duration, a.source_in, a.channel) == (3600, 5, 36002, 1)
    assert a.gain_db == -6.0 and a.file_hint == "/Volumes/Sound/Day 1/12A_T3.wav"
    assert (b.record_in, b.source_in, b.channel) == (3605, 36010, 1)
    assert b.crossfade_in == 2 and b.crossfade_pre == 1
    assert [(c.record_in, c.channel) for c in tl.tracks[1].clips] == [(3600, 2)]


def test_multicam_audio_angle(tl):
    (mc,) = tl.tracks[4].clips
    assert (mc.record_in, mc.duration, mc.source_in) == (3615, 2, 36020)


def test_connected_and_compound(tl):
    music = tl.tracks[2].clips
    assert [(c.record_in, c.duration, c.source_in) for c in music] == [(3601, 2, 0), (3610, 5, 25)]
    (over,) = tl.tracks[3].clips
    assert over.record_in == F(7203, 2)


def test_loose_clips_rejected(tmp_path):
    p = tmp_path / "e.fcpxml"
    p.write_text('<fcpxml version="1.10"><resources/><library><event><asset-clip/></event></library></fcpxml>')
    with pytest.raises(ValueError, match="proyecto"):
        read_fcpxml(p)


def test_fcpxmld_bundle(tmp_path):
    d = tmp_path / "p.fcpxmld"
    d.mkdir()
    (d / "Info.fcpxml").write_text(FCPXML)
    assert read_fcpxml(d).name == "P1"


PIC_FCPXML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
 <resources>
  <format id="r1" frameDuration="1/25s"/>
  <asset id="r2" name="A001C002" start="36000s" duration="60s" hasVideo="1" hasAudio="1" audioChannels="2">
   <media-rep kind="original-media" src="file:///Volumes/Cam/A001C002.mov"/>
   <metadata>
    <md key="com.apple.proapps.studio.scene" value="5 12"/>
    <md key="com.apple.proapps.studio.take" value="3"/>
    <md key="com.apple.proapps.studio.reel" value="A001"/>
   </metadata>
  </asset>
  <asset id="r3" name="Music" start="0s" duration="10s" hasVideo="0" hasAudio="1" audioChannels="2">
   <media-rep kind="original-media" src="file:///Volumes/Music/music.wav"/>
  </asset>
 </resources>
 <library><event name="E"><project name="P">
  <sequence format="r1" tcStart="3600s" tcFormat="NDF"><spine>
   <asset-clip ref="r2" offset="3600s" start="36001s" duration="2s" name="A001C002"/>
   <asset-clip ref="r2" offset="3602s" start="36010s" duration="3s" name="A001C002 b">
    <metadata><md key="com.apple.proapps.studio.take" value="9"/></metadata>
   </asset-clip>
   <asset-clip ref="r3" offset="3605s" start="0s" duration="1s" name="Music"/>
  </spine></sequence>
 </project></event></library>
</fcpxml>
"""


def test_picture_mode_reads_video_clips_with_metadata(tmp_path):
    p = tmp_path / "pic.fcpxml"
    p.write_text(PIC_FCPXML)
    tl = read_fcpxml(p, picture=True)
    assert tl.picture and [t.name for t in tl.tracks] == ["V"]
    a, b = tl.tracks[0].clips  # the audio-only asset is skipped
    assert (a.record_in, a.duration, a.source_in, a.channel) == (3600, 2, 36001, None)
    assert (a.scene, a.take, a.reel) == ("5 12", "3", "A001")
    assert a.file_hint == "/Volumes/Cam/A001C002.mov"
    assert (b.take, b.scene) == ("9", "5 12")  # clip metadata wins over the asset's


def test_audio_mode_reads_audio_of_all_assets(tmp_path):
    p = tmp_path / "pic.fcpxml"
    p.write_text(PIC_FCPXML)
    tl = read_fcpxml(p)
    assert not tl.picture and len(list(tl.clips())) == 6  # 2 camera clips x 2 channels + the music asset x 2 channels
