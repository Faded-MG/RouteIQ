import { vi } from "vitest";

type MapHandler = () => void;
type SourceOptions = { type: string; data: unknown };

const NativeMap = globalThis.Map;

export class MockGeoJSONSource {
  readonly type = "geojson";
  data: unknown;
  readonly setData = vi.fn((data: unknown) => {
    this.data = data;
  });

  constructor(data: unknown) {
    this.data = data;
  }
}

export class Map {
  readonly sources = new NativeMap<string, MockGeoJSONSource>();
  readonly layers: Array<Record<string, unknown>> = [];
  readonly handlers = new NativeMap<string, MapHandler[]>();
  readonly addSource = vi.fn((id: string, options: SourceOptions) => {
    this.sources.set(id, new MockGeoJSONSource(options.data));
  });
  readonly getSource = vi.fn((id: string) => this.sources.get(id));
  readonly addLayer = vi.fn((layer: Record<string, unknown>) => {
    this.layers.push(layer);
  });
  readonly setPaintProperty = vi.fn();
  readonly moveLayer = vi.fn();
  readonly fitBounds = vi.fn();
  readonly resize = vi.fn();
  readonly setStyle = vi.fn(() => {
    this.sources.clear();
    this.layers.length = 0;
    queueMicrotask(() => this.emit("style.load"));
    return this;
  });
  readonly addControl = vi.fn();
  readonly removeControl = vi.fn();
  readonly remove = vi.fn();
  readonly on = vi.fn((event: string, handler: MapHandler) => {
    const handlers = this.handlers.get(event) ?? [];
    handlers.push(handler);
    this.handlers.set(event, handlers);
    if (event === "load") queueMicrotask(handler);
    return this;
  });
  readonly off = vi.fn((event: string, handler: MapHandler) => {
    this.handlers.set(
      event,
      (this.handlers.get(event) ?? []).filter((registered) => registered !== handler),
    );
    return this;
  });

  constructor(_options: Record<string, unknown>) {
    maplibreMockState.maps.push(this);
  }

  emit(event: string): void {
    for (const handler of this.handlers.get(event) ?? []) handler();
  }
}

export class Marker {
  readonly element: HTMLElement;
  readonly setLngLat = vi.fn(() => this);
  readonly setPopup = vi.fn(() => this);
  readonly addTo = vi.fn(() => this);
  readonly remove = vi.fn(() => this);

  constructor(options: { element?: HTMLElement } = {}) {
    this.element = options.element ?? document.createElement("div");
    maplibreMockState.markers.push(this);
  }
}

export class Popup {
  readonly setDOMContent = vi.fn(() => this);

  constructor(_options?: Record<string, unknown>) {}
}

export class AttributionControl {
  constructor(_options?: Record<string, unknown>) {}
}

export class NavigationControl {
  constructor(_options?: Record<string, unknown>) {}
}

export const maplibreMockState: {
  maps: Map[];
  markers: Marker[];
} = {
  maps: [],
  markers: [],
};

export function resetMapLibreMocks(): void {
  maplibreMockState.maps = [];
  maplibreMockState.markers = [];
}
