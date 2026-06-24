import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react'
import type { OverlayObject, OverlayPayload } from '../types'

interface VideoOverlayPlayerProps {
  sourceUrl: string
  overlay: OverlayPayload
  seekRequest: number | null
}

interface Rect {
  x: number
  y: number
  w: number
  h: number
}

interface CardRect extends Rect {
  name: string
}

interface ScaledObject extends OverlayObject {
  key: string
  rect: Rect
}

interface Connector {
  key: string
  color: string
  points: string
  start: { x: number; y: number }
}

interface VideoContentRect {
  left: number
  top: number
  width: number
  height: number
}

interface OverlayLayout {
  objects: ScaledObject[]
  cards: { object: ScaledObject; rect: CardRect }[]
  cardKeys: Set<string>
  connectors: Connector[]
}

const EMPTY_LAYOUT: OverlayLayout = {
  objects: [],
  cards: [],
  cardKeys: new Set(),
  connectors: [],
}

const EMPTY_VIDEO_CONTENT_RECT: VideoContentRect = {
  left: 0,
  top: 0,
  width: 0,
  height: 0,
}

export function VideoOverlayPlayer({
  sourceUrl,
  overlay,
  seekRequest,
}: VideoOverlayPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const slotByObjectRef = useRef(new Map<string, string>())
  const [currentFrame, setCurrentFrame] = useState(0)
  const [videoContentRect, setVideoContentRect] = useState<VideoContentRect>(
    EMPTY_VIDEO_CONTENT_RECT,
  )
  const [layout, setLayout] = useState<OverlayLayout>(EMPTY_LAYOUT)

  const frameMap = useMemo(
    () =>
      new Map(
        overlay.frames.map((frame) => [frame.frame_index, frame.objects]),
      ),
    [overlay.frames],
  )
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

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const updateSize = () => {
      const nextRect = getVideoContentRect(video, overlay.video)
      setVideoContentRect((previousRect) =>
        isSameContentRect(previousRect, nextRect) ? previousRect : nextRect,
      )
    }
    updateSize()

    const observer = new ResizeObserver(updateSize)
    observer.observe(video)
    video.addEventListener('loadedmetadata', updateSize)
    return () => {
      observer.disconnect()
      video.removeEventListener('loadedmetadata', updateSize)
    }
  }, [overlay.video])

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const fps = overlay.video.fps || 25
    let animationFrameId = 0
    let videoFrameId = 0
    let disposed = false

    const updateFrame = (mediaTime: number) => {
      const nextFrame = Math.round(mediaTime * fps)
      setCurrentFrame((previous) =>
        previous === nextFrame ? previous : nextFrame,
      )
    }

    const updateFromVideo = () => updateFrame(video.currentTime)

    const animationTick = () => {
      updateFromVideo()
      if (!disposed && !video.paused && !video.ended) {
        animationFrameId = requestAnimationFrame(animationTick)
      }
    }

    const videoFrameTick: VideoFrameRequestCallback = (_now, metadata) => {
      updateFrame(metadata.mediaTime)
      if (!disposed) {
        videoFrameId = video.requestVideoFrameCallback(videoFrameTick)
      }
    }

    const start = () => {
      if ('requestVideoFrameCallback' in video) {
        if (!videoFrameId) {
          videoFrameId = video.requestVideoFrameCallback(videoFrameTick)
        }
      } else if (!animationFrameId) {
        animationFrameId = requestAnimationFrame(animationTick)
      }
    }

    video.addEventListener('loadedmetadata', updateFromVideo)
    video.addEventListener('seeked', updateFromVideo)
    video.addEventListener('timeupdate', updateFromVideo)
    video.addEventListener('play', start)
    video.addEventListener('pause', updateFromVideo)
    start()

    return () => {
      disposed = true
      video.removeEventListener('loadedmetadata', updateFromVideo)
      video.removeEventListener('seeked', updateFromVideo)
      video.removeEventListener('timeupdate', updateFromVideo)
      video.removeEventListener('play', start)
      video.removeEventListener('pause', updateFromVideo)
      if (animationFrameId) cancelAnimationFrame(animationFrameId)
      if (videoFrameId) video.cancelVideoFrameCallback(videoFrameId)
    }
  }, [overlay.video.fps])

  useEffect(() => {
    setLayout(
      buildOverlayLayout(
        frameMap.get(currentFrame) ?? [],
        videoContentRect,
        overlay.video,
        overlay.display?.max_cards_per_frame ?? 5,
        slotByObjectRef.current,
      ),
    )
  }, [
    currentFrame,
    frameMap,
    overlay.display?.max_cards_per_frame,
    overlay.video,
    videoContentRect,
  ])

  const overlayStyle = {
    left: videoContentRect.left,
    top: videoContentRect.top,
    width: videoContentRect.width,
    height: videoContentRect.height,
  } as CSSProperties

  return (
    <div className="video-shell">
      <video ref={videoRef} src={sourceUrl} controls preload="metadata" />
      <div className="video-overlay" style={overlayStyle}>
        <svg
          className="overlay-connectors"
          viewBox={`0 0 ${videoContentRect.width} ${videoContentRect.height}`}
          preserveAspectRatio="none"
        >
          {layout.connectors.map((connector) => (
            <g key={connector.key}>
              <polyline
                points={connector.points}
                fill="none"
                stroke={connector.color}
                strokeWidth="3.5"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              <circle
                cx={connector.start.x}
                cy={connector.start.y}
                r="5"
                fill={connector.color}
                stroke="rgba(255,255,255,0.9)"
                strokeWidth="2.5"
              />
            </g>
          ))}
        </svg>

        {layout.objects.map((object) => (
          <OverlayBox
            key={object.key}
            object={object}
            emphasized={layout.cardKeys.has(object.key)}
          />
        ))}

        {layout.cards.map(({ object, rect }) => (
          <OverlayCard key={object.key} object={object} rect={rect} />
        ))}
      </div>
    </div>
  )
}

function getVideoContentRect(
  videoElement: HTMLVideoElement,
  video: OverlayPayload['video'],
): VideoContentRect {
  const elementRect = videoElement.getBoundingClientRect()
  const elementWidth = elementRect.width
  const elementHeight = elementRect.height
  const sourceWidth = videoElement.videoWidth || video.width
  const sourceHeight = videoElement.videoHeight || video.height

  if (
    elementWidth <= 0 ||
    elementHeight <= 0 ||
    sourceWidth <= 0 ||
    sourceHeight <= 0
  ) {
    return EMPTY_VIDEO_CONTENT_RECT
  }

  const elementRatio = elementWidth / elementHeight
  const sourceRatio = sourceWidth / sourceHeight

  if (elementRatio > sourceRatio) {
    const height = elementHeight
    const width = height * sourceRatio
    return {
      left: (elementWidth - width) / 2,
      top: 0,
      width,
      height,
    }
  }

  const width = elementWidth
  const height = width / sourceRatio
  return {
    left: 0,
    top: (elementHeight - height) / 2,
    width,
    height,
  }
}

function isSameContentRect(
  first: VideoContentRect,
  second: VideoContentRect,
): boolean {
  return (
    Math.abs(first.left - second.left) < 0.5 &&
    Math.abs(first.top - second.top) < 0.5 &&
    Math.abs(first.width - second.width) < 0.5 &&
    Math.abs(first.height - second.height) < 0.5
  )
}

function buildOverlayLayout(
  objects: OverlayObject[],
  size: VideoContentRect,
  video: OverlayPayload['video'],
  maxCards: number,
  slotByObject: Map<string, string>,
): OverlayLayout {
  if (size.width <= 0 || size.height <= 0) {
    return EMPTY_LAYOUT
  }

  const scaleX = size.width / Math.max(1, video.width)
  const scaleY = size.height / Math.max(1, video.height)
  const scaledObjects = objects.map((object) =>
    scaleObject(object, scaleX, scaleY),
  )
  const cardObjects = [...scaledObjects]
    .sort(
      (first, second) =>
        (second.card_priority ?? 0) - (first.card_priority ?? 0),
    )
    .slice(0, maxCards)
  const cardKeys = new Set(cardObjects.map((object) => object.key))
  const occupied = scaledObjects.map((object) => object.rect)
  const cards: { object: ScaledObject; rect: CardRect }[] = []
  const connectors: Connector[] = []

  for (const object of cardObjects) {
    const rect = chooseCardSlot(
      object,
      occupied,
      size.width,
      size.height,
      slotByObject,
    )
    occupied.push(rect)
    cards.push({ object, rect })
    connectors.push(createConnector(object, rect))
  }

  return { objects: scaledObjects, cards, cardKeys, connectors }
}

function scaleObject(
  object: OverlayObject,
  scaleX: number,
  scaleY: number,
): ScaledObject {
  const [x1, y1, x2, y2] = object.bbox
  return {
    ...object,
    key: objectKey(object),
    rect: {
      x: x1 * scaleX,
      y: y1 * scaleY,
      w: Math.max(1, (x2 - x1) * scaleX),
      h: Math.max(1, (y2 - y1) * scaleY),
    },
  }
}

function objectKey(object: OverlayObject): string {
  return String(
    object.object_id ??
      object.track_id ??
      `${object.bbox[0]}-${object.bbox[1]}`,
  )
}

function chooseCardSlot(
  object: ScaledObject,
  occupied: Rect[],
  width: number,
  height: number,
  slotByObject: Map<string, string>,
): CardRect {
  const compact = width < 900
  const cardWidth = compact ? 224 : 286
  const cardHeight = compact ? 194 : 244
  const margin = compact ? 8 : 16
  const bottomSafe = compact ? 58 : 82
  const slots = buildSlots(
    width,
    height,
    cardWidth,
    cardHeight,
    margin,
    bottomSafe,
  )
  const previousSlot = slotByObject.get(object.key)
  let best = slots[0]
  let bestPenalty = Number.POSITIVE_INFINITY

  for (const slot of slots) {
    let penalty = occupied.reduce(
      (sum, rect) => sum + intersectionArea(slot, rect),
      0,
    )
    penalty += distancePenalty(slot, object.rect)
    if (previousSlot === slot.name) penalty -= 7000
    if (penalty < bestPenalty) {
      bestPenalty = penalty
      best = slot
    }
  }

  slotByObject.set(object.key, best.name)
  return best
}

function buildSlots(
  width: number,
  height: number,
  cardWidth: number,
  cardHeight: number,
  margin: number,
  bottomSafe: number,
): CardRect[] {
  const centerX = (width - cardWidth) / 2
  const maxY = Math.max(margin, height - cardHeight - bottomSafe)
  const centerY = (margin + maxY) / 2
  const slots: CardRect[] = [
    {
      name: 'top-left',
      x: margin,
      y: margin,
      w: cardWidth,
      h: cardHeight,
    },
    {
      name: 'top-right',
      x: width - cardWidth - margin,
      y: margin,
      w: cardWidth,
      h: cardHeight,
    },
    {
      name: 'middle-left',
      x: margin,
      y: centerY,
      w: cardWidth,
      h: cardHeight,
    },
    {
      name: 'middle-right',
      x: width - cardWidth - margin,
      y: centerY,
      w: cardWidth,
      h: cardHeight,
    },
    {
      name: 'bottom-left',
      x: margin,
      y: maxY,
      w: cardWidth,
      h: cardHeight,
    },
    {
      name: 'bottom-right',
      x: width - cardWidth - margin,
      y: maxY,
      w: cardWidth,
      h: cardHeight,
    },
    {
      name: 'top-center',
      x: centerX,
      y: margin,
      w: cardWidth,
      h: cardHeight,
    },
    {
      name: 'bottom-center',
      x: centerX,
      y: maxY,
      w: cardWidth,
      h: cardHeight,
    },
  ]

  return slots.map((slot) => ({
    ...slot,
    x: Math.max(margin, Math.min(slot.x, width - slot.w - margin)),
    y: Math.max(margin, Math.min(slot.y, height - slot.h - bottomSafe)),
  }))
}

function intersectionArea(first: Rect, second: Rect): number {
  const width = Math.max(
    0,
    Math.min(first.x + first.w, second.x + second.w) -
      Math.max(first.x, second.x),
  )
  const height = Math.max(
    0,
    Math.min(first.y + first.h, second.y + second.h) -
      Math.max(first.y, second.y),
  )
  return width * height
}

function distancePenalty(first: Rect, second: Rect): number {
  const firstCenter = center(first)
  const secondCenter = center(second)
  return (
    Math.hypot(
      firstCenter.x - secondCenter.x,
      firstCenter.y - secondCenter.y,
    ) * 0.08
  )
}

function createConnector(
  object: ScaledObject,
  card: CardRect,
): Connector {
  const start = nearestPoint(object.rect, center(card))
  const end = nearestPoint(card, center(object.rect))
  const middleX = (start.x + end.x) / 2
  return {
    key: object.key,
    color: object.color,
    start,
    points: `${start.x},${start.y} ${middleX},${start.y} ${middleX},${end.y} ${end.x},${end.y}`,
  }
}

function center(rect: Rect) {
  return { x: rect.x + rect.w / 2, y: rect.y + rect.h / 2 }
}

function nearestPoint(rect: Rect, target: { x: number; y: number }) {
  return {
    x: Math.max(rect.x, Math.min(target.x, rect.x + rect.w)),
    y: Math.max(rect.y, Math.min(target.y, rect.y + rect.h)),
  }
}

function OverlayBox({
  object,
  emphasized,
}: {
  object: ScaledObject
  emphasized: boolean
}) {
  return (
    <div
      className="overlay-box"
      style={{
        '--box-color': object.color,
        left: object.rect.x,
        top: object.rect.y,
        width: object.rect.w,
        height: object.rect.h,
        borderWidth: emphasized ? 3 : 2,
      } as CSSProperties}
    >
      <span>{object.label}</span>
    </div>
  )
}

function OverlayCard({
  object,
  rect,
}: {
  object: ScaledObject
  rect: CardRect
}) {
  const metrics: {
    icon: MetricIconName
    label: string
    value: string
  }[] = [
    { icon: 'class', label: 'Class', value: object.label },
    {
      icon: 'detection',
      label: 'Detection confidence',
      value: formatPercent(object.det_conf),
    },
    {
      icon: 'brand',
      label: 'Brand confidence',
      value: formatBrandConfidence(object),
    },
    {
      icon: 'area',
      label: 'Area in frame',
      value: formatAreaPercent(object.area_ratio),
    },
    {
      icon: 'visibility',
      label: 'Visibility score',
      value: formatScore(object.visibility_score),
    },
    {
      icon: 'score',
      label: 'Overall score',
      value: formatScore(object.overall_score),
    },
  ]

  return (
    <div
      className="overlay-info-card"
      style={{
        '--box-color': object.color,
        left: rect.x,
        top: rect.y,
        width: rect.w,
        height: rect.h,
      } as CSSProperties}
    >
      {metrics.map((metric) => (
        <div className="overlay-metric" key={metric.label}>
          <MetricIcon name={metric.icon} />
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </div>
      ))}
    </div>
  )
}

type MetricIconName =
  | 'class'
  | 'detection'
  | 'brand'
  | 'area'
  | 'visibility'
  | 'score'

function MetricIcon({ name }: { name: MetricIconName }) {
  const paths: Record<MetricIconName, ReactNode> = {
    class: (
      <>
        <path d="M20.6 13.4 11 3.8A2.8 2.8 0 0 0 9 3H4a1 1 0 0 0-1 1v5c0 .8.3 1.5.8 2l9.6 9.6a2 2 0 0 0 2.8 0l4.4-4.4a2 2 0 0 0 0-2.8Z" />
        <circle cx="7.5" cy="7.5" r="1.5" />
      </>
    ),
    detection: (
      <>
        <path d="M4 19v-7M9 19V8M14 19v-4M19 19V5" />
      </>
    ),
    brand: (
      <>
        <path d="M12 3 4 7v10l8 4 8-4V7l-8-4Z" />
        <path d="m4 7 8 4 8-4M12 11v10" />
      </>
    ),
    area: <rect x="4" y="4" width="16" height="16" rx="2" />,
    visibility: (
      <>
        <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z" />
        <circle cx="12" cy="12" r="3" />
      </>
    ),
    score: (
      <path d="m12 3 2.9 5.9 6.5.9-4.7 4.6 1.1 6.5-5.8-3.1-5.8 3.1 1.1-6.5-4.7-4.6 6.5-.9L12 3Z" />
    ),
  }

  return (
    <svg
      className="overlay-metric-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  )
}

function formatPercent(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0%'
  return `${Math.round(value * 100)}%`
}

function formatAreaPercent(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0%'
  const percent = value * 100
  if (percent < 0.1) return '<0.1%'
  if (percent < 10) return `${percent.toFixed(1)}%`
  return `${Math.round(percent)}%`
}

function formatBrandConfidence(object: OverlayObject): string {
  if (
    object.brand === 'other' &&
    (!object.brand_conf || object.brand_conf <= 0)
  ) {
    return 'n/a'
  }
  return formatPercent(object.brand_conf)
}

function formatScore(value: number): string {
  if (!Number.isFinite(value)) return '0.00'
  return value.toFixed(2)
}
