/* Stroke icons drawn inline so the page loads no icon font and no external request. */
const PATHS: Record<string, string> = {
  home: 'M3 10.5 12 3l9 7.5M5.5 9.5V20h13V9.5',
  link: 'M10 13.5a4 4 0 0 0 5.7 0l2.8-2.8a4 4 0 0 0-5.7-5.7L11.5 6.3M14 10.5a4 4 0 0 0-5.7 0l-2.8 2.8a4 4 0 1 0 5.7 5.7l1.3-1.3',
  doc: 'M6 3h7l5 5v13H6zM13 3v5h5',
  chat: 'M4 5h16v11H9l-5 4z',
  grid: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',
  ticket: 'M12 3 21 12l-9 9-9-9z',
  people: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM2.5 20a6.5 6.5 0 0 1 13 0M17 11.5a3 3 0 1 0 0-6M18 20h3.5a5.5 5.5 0 0 0-4-5.3',
  nodes: 'M12 3.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5ZM5.5 15.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5ZM18.5 15.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5ZM12 8.5v3.5M12 12H5.5v3.5M12 12h6.5v3.5',
  wrench: 'M20 5.5a5 5 0 0 1-6.6 6.2L5 20.1 3.9 19l8.4-8.4A5 5 0 0 1 18.5 4l-3 3 1.5 1.5 3-3Z',
  gear: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1v.3a2 2 0 1 1-4 0v-.2a1.6 1.6 0 0 0-2.8-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 3.5 14H3a2 2 0 1 1 0-4h.2a1.6 1.6 0 0 0 1.1-2.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 10 3.5V3a2 2 0 1 1 4 0v.2a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7h.3a2 2 0 1 1 0 4h-.2a1.6 1.6 0 0 0-1.3 1Z',
  chevron: 'm9 5 7 7-7 7',
  refresh: 'M20 11a8 8 0 1 0-.7 4M20 5v6h-6',
  lock: 'M6 10V7a6 6 0 0 1 12 0v3M4.5 10h15v10h-15z',
  database: 'M12 3c4.4 0 8 1.3 8 3s-3.6 3-8 3-8-1.3-8-3 3.6-3 8-3ZM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6',
  warn: 'M12 3 22 20H2L12 3ZM12 9v5M12 17.2v.1',
  send: 'M4 12 21 4l-8 17-2.2-6.8L4 12Z',
  search: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM20 20l-4-4',
  external: 'M14 4h6v6M20 4l-9 9M18 14v6H4V6h6',
  check: 'm4 12.5 5 5L20 6',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 7v5.2l3.4 2',
}

export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] ?? PATHS.doc} />
    </svg>
  )
}
