export function keepListItemVisible(container, item) {
  if (!container || !item) return;
  const containerRect = container.getBoundingClientRect();
  const itemRect = item.getBoundingClientRect();
  if (itemRect.top < containerRect.top) {
    container.scrollTop -= containerRect.top - itemRect.top;
  } else if (itemRect.bottom > containerRect.bottom) {
    container.scrollTop += itemRect.bottom - containerRect.bottom;
  }
}
