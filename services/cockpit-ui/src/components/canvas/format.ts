export function formatPrice(value: number): string {
  return `$${value.toLocaleString('en-US', {
    minimumFractionDigits: value < 1000 ? 2 : 1,
    maximumFractionDigits: value < 1000 ? 2 : 1,
  })}`
}
