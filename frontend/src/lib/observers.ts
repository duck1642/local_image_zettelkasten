export type ObserverCleanup = () => void;

export function watchIntersection(
  node: HTMLElement,
  options: { rootMargin?: string; onEnter: () => void }
): ObserverCleanup {
  const observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) options.onEnter();
  }, { rootMargin: options.rootMargin || '0px' });
  observer.observe(node);
  return () => observer.disconnect();
}

export function watchResize(
  node: HTMLElement,
  onResize: (width: number, height: number) => void
): ObserverCleanup {
  onResize(Math.floor(node.clientWidth), Math.floor(node.clientHeight));
  const observer = new ResizeObserver(([entry]) => {
    onResize(Math.floor(entry.contentRect.width), Math.floor(entry.contentRect.height));
  });
  observer.observe(node);
  return () => observer.disconnect();
}
