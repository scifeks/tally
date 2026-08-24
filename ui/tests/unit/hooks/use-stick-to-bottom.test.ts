import { createElement } from 'react'
import { describe, it, expect } from 'vitest'
import { render, renderHook, act, fireEvent, screen } from '@testing-library/react'
import { isAtBottom, useStickToBottom } from '@/hooks/use-stick-to-bottom'

function makeContainer(
  scrollTop: number,
  scrollHeight = 1000,
  clientHeight = 100
): HTMLDivElement {
  const el = document.createElement('div')
  Object.defineProperty(el, 'scrollHeight', {
    value: scrollHeight,
    configurable: true,
  })
  Object.defineProperty(el, 'clientHeight', {
    value: clientHeight,
    configurable: true,
  })
  el.scrollTop = scrollTop
  return el
}

function Harness() {
  const {
    containerRef,
    showJumpButton,
    scrollToBottom,
    stickToBottom,
    handleScroll,
  } = useStickToBottom<HTMLDivElement>()
  return createElement(
    'div',
    null,
    createElement(
      'div',
      {
        ref: containerRef,
        'data-testid': 'log',
        onScroll: handleScroll,
      },
      showJumpButton
        ? createElement('span', { 'data-testid': 'jump' })
        : null
    ),
    createElement('button', {
      'data-testid': 'stick',
      onClick: stickToBottom,
    }),
    createElement('button', {
      'data-testid': 'rejoin',
      onClick: scrollToBottom,
    })
  )
}

function setMetrics(
  el: HTMLElement,
  scrollTop: number,
  scrollHeight = 1000,
  clientHeight = 100
): void {
  Object.defineProperty(el, 'scrollHeight', {
    value: scrollHeight,
    configurable: true,
  })
  Object.defineProperty(el, 'clientHeight', {
    value: clientHeight,
    configurable: true,
  })
  el.scrollTop = scrollTop
}

function touch(el: HTMLElement, type: string, clientY: number): void {
  const event = new Event(type, { bubbles: true })
  Object.defineProperty(event, 'touches', {
    value: [{ clientY }],
  })
  el.dispatchEvent(event)
}

const jump = () => screen.queryByTestId('jump')

describe('isAtBottom', () => {
  it.each([
    { scrollTop: 900, expected: true },
    { scrollTop: 896, expected: true },
    { scrollTop: 895, expected: false },
    { scrollTop: 0, expected: false },
  ])(
    'treats scrollTop $scrollTop as at-bottom=$expected',
    ({ scrollTop, expected }) => {
      expect(
        isAtBottom({ scrollTop, scrollHeight: 1000, clientHeight: 100 })
      ).toBe(expected)
    }
  )

  it('counts content shorter than the viewport as at the bottom', () => {
    expect(
      isAtBottom({ scrollTop: 0, scrollHeight: 80, clientHeight: 100 })
    ).toBe(true)
  })
})

describe('useStickToBottom', () => {
  it('follows the bottom while pinned', () => {
    const { result } = renderHook(() =>
      useStickToBottom<HTMLDivElement>()
    )
    const el = makeContainer(900)
    result.current.containerRef.current = el

    act(() => result.current.stickToBottom())

    expect(el.scrollTop).toBe(1000)
    expect(result.current.showJumpButton).toBe(false)
  })

  it('releases the follow on a wheel-up', () => {
    render(createElement(Harness))
    fireEvent.wheel(screen.getByTestId('log'), { deltaY: -30 })
    expect(jump()).toBeInTheDocument()
  })

  it('ignores a downward wheel', () => {
    render(createElement(Harness))
    fireEvent.wheel(screen.getByTestId('log'), { deltaY: 30 })
    expect(jump()).not.toBeInTheDocument()
  })

  it('releases on a touch drag down the screen', () => {
    render(createElement(Harness))
    const log = screen.getByTestId('log')
    act(() => {
      touch(log, 'touchstart', 100)
      touch(log, 'touchmove', 140)
    })
    expect(jump()).toBeInTheDocument()
  })

  it('keeps following when a touch drags up', () => {
    render(createElement(Harness))
    const log = screen.getByTestId('log')
    act(() => {
      touch(log, 'touchstart', 140)
      touch(log, 'touchmove', 100)
    })
    expect(jump()).not.toBeInTheDocument()
  })

  it('stays released after a small upward nudge while streaming', () => {
    render(createElement(Harness))
    const log = screen.getByTestId('log')
    setMetrics(log, 900)

    fireEvent.wheel(log, { deltaY: -30 })
    log.scrollTop = 870
    fireEvent.scroll(log)
    fireEvent.click(screen.getByTestId('stick'))

    expect(jump()).toBeInTheDocument()
    expect(log.scrollTop).toBe(870)
  })

  it('re-engages when the reader returns to the bottom', () => {
    render(createElement(Harness))
    const log = screen.getByTestId('log')
    setMetrics(log, 900)

    fireEvent.wheel(log, { deltaY: -30 })
    expect(jump()).toBeInTheDocument()

    log.scrollTop = 900
    fireEvent.scroll(log)
    expect(jump()).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('stick'))
    expect(log.scrollTop).toBe(1000)
  })

  it('jumps to bottom and re-pins after scrolling away', () => {
    render(createElement(Harness))
    const log = screen.getByTestId('log')
    setMetrics(log, 900)

    fireEvent.wheel(log, { deltaY: -30 })
    expect(jump()).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('rejoin'))
    expect(jump()).not.toBeInTheDocument()
    expect(log.scrollTop).toBe(1000)

    log.scrollTop = 950
    fireEvent.click(screen.getByTestId('stick'))
    expect(log.scrollTop).toBe(1000)
  })

  it('does not re-pin mid touch drag', () => {
    render(createElement(Harness))
    const log = screen.getByTestId('log')
    setMetrics(log, 900)

    fireEvent.wheel(log, { deltaY: -30 })
    act(() => touch(log, 'touchstart', 100))
    log.scrollTop = 900
    fireEvent.scroll(log)

    expect(jump()).toBeInTheDocument()
  })

  it('releases on an upward scroll without wheel or touch', () => {
    render(createElement(Harness))
    const log = screen.getByTestId('log')
    setMetrics(log, 900)

    log.scrollTop = 900
    fireEvent.scroll(log)

    log.scrollTop = 840
    fireEvent.scroll(log)

    expect(jump()).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('stick'))
    expect(log.scrollTop).toBe(840)
  })
})
