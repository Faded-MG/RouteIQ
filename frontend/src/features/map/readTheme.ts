export interface MapTheme {
  backgroundColor: string;
  routeColors: [string, string, string];
  mutedColor: string;
  textColor: string;
  surfaceColor: string;
  accentColor: string;
}

function readToken(style: CSSStyleDeclaration, name: string): string {
  const value = style.getPropertyValue(name).trim();
  if (!value) {
    throw new Error(`Missing theme token: ${name}`);
  }
  return value;
}

export function readTheme(root: HTMLElement = document.documentElement): MapTheme {
  const style = getComputedStyle(root);
  return {
    backgroundColor: readToken(style, "--color-bg"),
    routeColors: [
      readToken(style, "--color-route-a"),
      readToken(style, "--color-route-b"),
      readToken(style, "--color-route-c"),
    ],
    mutedColor: readToken(style, "--color-route-muted"),
    textColor: readToken(style, "--color-text"),
    surfaceColor: readToken(style, "--color-surface"),
    accentColor: readToken(style, "--color-accent"),
  };
}
