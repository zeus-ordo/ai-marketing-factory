import type { SupportedLocale } from "@/lib/i18n/translations";

export function formatCurrencyUSD(locale: SupportedLocale, amount: number) {
  const formatted = new Intl.NumberFormat(locale, {
    maximumFractionDigits: 0,
  }).format(amount);
  return `US$${formatted}`;
}

export function formatDateTime(locale: SupportedLocale, isoDateTime: string) {
  return new Date(isoDateTime).toLocaleString(locale);
}
