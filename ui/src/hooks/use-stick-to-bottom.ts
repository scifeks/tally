import { useCallback, useEffect, useRef, useState } from 'react'

const BOTTOM_EPSILON_PX = 4

const TOUCH_RELEASE_PX = 10

interface ScrollMetrics {
  scrollTop: number
  scrollHeight: number
  clientHeight: number
}

export function isAtBottom(
  { scrollTop, scrollHeight, clientHeight }: ScrollMetrics,
  threshold = BOTTOM_EPSILON_PX
): boolean {
  return scrollHeight - scrollTop - clientHeight <= threshold
}

export function useStickToBottom<T extends HTMLElement>() {
  const containerRef = useRef<T>(null)
  const pinnedRef = useRef(true)
  const touchingRef = useRef(false)
  const lastTopRef = useRef(0)
  const [showJumpButton, setShowJumpButton] = useState(false)

  const scrollToBottom = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
    lastTopRef.current = el.scrollTop
    pinnedRef.current = true
    setShowJumpButton(false)
  }, [])

  const stickToBottom = useCallback(() => {
    if (pinnedRef.current) scrollToBottom()
  }, [scrollToBottom])

  const release = useCallback(() => {
    if (!pinnedRef.current) return
    pinnedRef.current = false
    setShowJumpButton(true)
  }, [])

  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const top = el.scrollTop
    const movedUp = top < lastTopRef.current - 1
    lastTopRef.current = top
    if (touchingRef.current) return
    if (movedUp && !isAtBottom(el)) {
      release()
      return
    }
    if (isAtBottom(el)) {
      pinnedRef.current = true
      setShowJumpButton(false)
    } else if (!pinnedRef.current) {
      setShowJumpButton(true)
    }
  }, [release])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const onWheel = (e: WheelEvent) => {
      if (e.deltaY < 0) release()
    }

    let startY = 0
    const onTouchStart = (e: TouchEvent) => {
      touchingRef.current = true
      startY = e.touches[0]?.clientY ?? 0
    }
    const onTouchMove = (e: TouchEvent) => {
      const y = e.touches[0]?.clientY ?? startY
      if (y - startY > TOUCH_RELEASE_PX) release()
    }
    const onTouchEnd = () => {
      touchingRef.current = false
      handleScroll()
    }

    el.addEventListener('wheel', onWheel, { passive: true })
    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchmove', onTouchMove, { passive: true })
    el.addEventListener('touchend', onTouchEnd, { passive: true })
    el.addEventListener('touchcancel', onTouchEnd, { passive: true })
    return () => {
      el.removeEventListener('wheel', onWheel)
      el.removeEventListener('touchstart', onTouchStart)
      el.removeEventListener('touchmove', onTouchMove)
      el.removeEventListener('touchend', onTouchEnd)
      el.removeEventListener('touchcancel', onTouchEnd)
    }
  }, [release, handleScroll])

  return { containerRef, showJumpButton, scrollToBottom, stickToBottom, handleScroll }
}
