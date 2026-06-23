import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from 'react'
import type { OverlayObject, OverlayPayload } from '../types'

interface VideoOverlayPlayerProps {
  sourceUrl: string
  overlay: OverlayPayload
  seekRequest: number | null
}

export function VideoOverlayPlayer({
  sourceUrl,
  overlay,
  seekRequest,
}: VideoOverlayPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [currentFrame, setCurrentFrame] = useState(0)

  const frameMap = useMemo(
    () =>
      new Map(
        overlay.frames.map((frame) => [frame.frame_index, frame.objects]),
      ),
    [overlay],
  )
  const objects = frameMap.get(currentFrame) ?? []

  useEffect(() => {
    const video = videoRef.current
    if (
      seekRequest !== null &&
      video &&
      Math.abs(video.currentTime - seekRequest) > 0.15
    ) {
      video.currentTime = seekRequest
    }
  }, [seekRequest])

  const updateFrame = () => {
    const video = videoRef.current
    if (!video) return
    setCurrentFrame(Math.round(video.currentTime * (overlay.video.fps || 25)))
  }

  return (
    <div className="video-shell">
      <video
        ref={videoRef}
        src={sourceUrl}
        controls
        preload="metadata"
        onTimeUpdate={updateFrame}
        onSeeked={updateFrame}
      />
      <div className="video-overlay">
        {objects.map((object, index) => (
          <OverlayBox
            key={`${object.object_id ?? object.track_id}-${index}`}
            object={object}
            videoWidth={overlay.video.width}
            videoHeight={overlay.video.height}
          />
        ))}
      </div>
    </div>
  )
}

function OverlayBox({
  object,
  videoWidth,
  videoHeight,
}: {
  object: OverlayObject
  videoWidth: number
  videoHeight: number
}) {
  const [x1, y1, x2, y2] = object.bbox
  return (
    <div
      className="overlay-box"
      style={{
        '--box-color': object.color,
        left: `${(x1 / videoWidth) * 100}%`,
        top: `${(y1 / videoHeight) * 100}%`,
        width: `${((x2 - x1) / videoWidth) * 100}%`,
        height: `${((y2 - y1) / videoHeight) * 100}%`,
      } as CSSProperties}
    >
      <span>{object.label}</span>
    </div>
  )
}
