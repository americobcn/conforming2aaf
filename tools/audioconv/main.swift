// audioconv: read any audio file CoreAudio understands and write raw 24-bit packed
// little-endian PCM (the data of a WAV chunk). Uses AudioToolbox (ExtAudioFile reads and
// decodes to float32; AudioConverter does the float -> 24-bit conversion). Chunks
// (bext, iXML...) are not touched here: the Python engine writes the RIFF container.
//
//   audioconv --in FILE [--channel N] [--out PATH|-]
//     --channel N  1-based channel to extract; 0 (default) keeps all channels interleaved
//     --out        raw PCM destination, "-" (default) is stdout
//   stderr, on success: {"frames":N,"channels":C,"clipped":K,"peak":P}
//   clipped counts samples beyond +-1.0 (0 dBFS), which the 24-bit range cannot hold.
import AudioToolbox
import Foundation

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data("audioconv: \(message)\n".utf8))
    exit(1)
}

func check(_ status: OSStatus, _ what: String) {
    if status != noErr { fail("\(what) failed (OSStatus \(status))") }
}

var input = ""
var channel = 0
var output = "-"
var args = CommandLine.arguments.dropFirst().makeIterator()
while let arg = args.next() {
    switch arg {
    case "--in": input = args.next() ?? ""
    case "--channel": channel = Int(args.next() ?? "") ?? -1
    case "--out": output = args.next() ?? ""
    default: fail("unknown argument \(arg)")
    }
}
if input.isEmpty || channel < 0 { fail("usage: audioconv --in FILE [--channel N] [--out PATH|-]") }

var file: ExtAudioFileRef?
check(ExtAudioFileOpenURL(URL(fileURLWithPath: input) as CFURL, &file), "open \(input)")
defer { ExtAudioFileDispose(file!) }

var fileFormat = AudioStreamBasicDescription()
var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
check(ExtAudioFileGetProperty(file!, kExtAudioFileProperty_FileDataFormat, &size, &fileFormat), "read format")
let channels = Int(fileFormat.mChannelsPerFrame)
if channel > channels { fail("channel \(channel) does not exist (file has \(channels))") }
let outChannels = channel == 0 ? channels : 1

func floatFormat(_ n: Int) -> AudioStreamBasicDescription {
    AudioStreamBasicDescription(
        mSampleRate: fileFormat.mSampleRate, mFormatID: kAudioFormatLinearPCM,
        mFormatFlags: kAudioFormatFlagsNativeFloatPacked, mBytesPerPacket: UInt32(4 * n),
        mFramesPerPacket: 1, mBytesPerFrame: UInt32(4 * n), mChannelsPerFrame: UInt32(n),
        mBitsPerChannel: 32, mReserved: 0)
}

var client = floatFormat(channels)  // interleaved float32, all channels
check(ExtAudioFileSetProperty(file!, kExtAudioFileProperty_ClientDataFormat,
                              UInt32(MemoryLayout<AudioStreamBasicDescription>.size), &client), "set client format")

var floatOut = floatFormat(outChannels)
var int24 = AudioStreamBasicDescription(
    mSampleRate: fileFormat.mSampleRate, mFormatID: kAudioFormatLinearPCM,
    mFormatFlags: kAudioFormatFlagIsSignedInteger | kAudioFormatFlagIsPacked,
    mBytesPerPacket: UInt32(3 * outChannels), mFramesPerPacket: 1, mBytesPerFrame: UInt32(3 * outChannels),
    mChannelsPerFrame: UInt32(outChannels), mBitsPerChannel: 24, mReserved: 0)
var converter: AudioConverterRef?
check(AudioConverterNew(&floatOut, &int24, &converter), "create converter")
defer { AudioConverterDispose(converter!) }

let sink: FileHandle
if output == "-" {
    sink = FileHandle.standardOutput
} else {
    FileManager.default.createFile(atPath: output, contents: nil)
    guard let handle = FileHandle(forWritingAtPath: output) else { fail("cannot write \(output)") }
    sink = handle
}

let blockFrames = 1 << 16
var interleaved = [Float](repeating: 0, count: blockFrames * channels)
var selected = [Float](repeating: 0, count: blockFrames * outChannels)
var packed = [UInt8](repeating: 0, count: blockFrames * outChannels * 3)
var totalFrames = 0
var clipped = 0
var peak: Float = 0

while true {
    var frames = UInt32(blockFrames)
    var list = AudioBufferList(
        mNumberBuffers: 1,
        mBuffers: AudioBuffer(mNumberChannels: UInt32(channels), mDataByteSize: UInt32(blockFrames * channels * 4), mData: nil))
    interleaved.withUnsafeMutableBytes { raw in
        list.mBuffers.mData = raw.baseAddress
        check(ExtAudioFileRead(file!, &frames, &list), "read")
    }
    let n = Int(frames)
    if n == 0 { break }
    if channel == 0 {
        for i in 0..<(n * channels) { selected[i] = interleaved[i] }
    } else {
        for i in 0..<n { selected[i] = interleaved[i * channels + channel - 1] }
    }
    for i in 0..<(n * outChannels) {
        let magnitude = abs(selected[i])
        if magnitude > peak { peak = magnitude }
        if magnitude > 1.0 { clipped += 1 }
    }
    var packedSize = UInt32(n * outChannels * 3)
    selected.withUnsafeBytes { src in
        packed.withUnsafeMutableBytes { dst in
            check(AudioConverterConvertBuffer(converter!, UInt32(n * outChannels * 4), src.baseAddress!, &packedSize,
                                              dst.baseAddress!), "convert")
        }
    }
    sink.write(Data(packed[0..<Int(packedSize)]))
    totalFrames += n
}
try? sink.close()
FileHandle.standardError.write(Data(
    "{\"frames\":\(totalFrames),\"channels\":\(outChannels),\"clipped\":\(clipped),\"peak\":\(peak)}\n".utf8))
