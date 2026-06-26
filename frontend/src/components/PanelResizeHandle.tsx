import { useCallback, useEffect, useRef } from 'react'

interface Props {
  onDrag: (deltaX: number) => void
  onDragEnd?: () => void
}

export function PanelResizeHandle({ onDrag, onDragEnd }: Props) {
  const dragging = useRef(false)
  const lastX = useRef(0)

  const onMouseDown = useCallback((event: React.MouseEvent) => {
    event.preventDefault()
    dragging.current = true
    lastX.current = event.clientX
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [])

  useEffect(() => {
    const onMouseMove = (event: MouseEvent) => {
      if (!dragging.current) return
      const delta = event.clientX - lastX.current
      lastX.current = event.clientX
      onDrag(delta)
    }

    const onMouseUp = () => {
      if (!dragging.current) return
      dragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      onDragEnd?.()
    }

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [onDrag, onDragEnd])

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize panel"
      className="w-1 shrink-0 cursor-col-resize bg-stone-300 transition-colors hover:bg-amber-500/60 active:bg-amber-600"
      onMouseDown={onMouseDown}
    />
  )
}
