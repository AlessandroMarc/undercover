const DAY_MS = 86_400_000;

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

const dateOnly = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

const dateTime = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

export function formatMoney(amount: number): string {
  return amount < 0 ? `−${money.format(-amount)}` : money.format(amount);
}

export function formatDate(date: string): string {
  return dateOnly.format(new Date(date));
}

export function formatDateTime(timestamp: string): string {
  return dateTime.format(new Date(timestamp)).replaceAll("\u202f", " ");
}

export function formatCount(count: number, noun: string): string {
  const label = count === 1 ? noun : `${noun}s`;
  return `${count.toLocaleString("en-US")} ${label}`;
}

export function formatRelative(timestamp: string, now: Date): string {
  const seconds = (now.getTime() - new Date(timestamp).getTime()) / 1000;
  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${String(minutes)} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24)
    return `${String(hours)} ${hours === 1 ? "hour" : "hours"} ago`;
  const days = Math.floor(seconds / (DAY_MS / 1000));
  if (days < 7) return `${String(days)} ${days === 1 ? "day" : "days"} ago`;
  return formatDateTime(timestamp);
}

export function humanize(code: string): string {
  const words = code.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
