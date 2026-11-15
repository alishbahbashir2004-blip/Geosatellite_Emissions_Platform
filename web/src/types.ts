// API response shapes. Only the fields the client reads are listed; gas
// result dicts carry many more keys than are typed here.

export interface BBox { N: number; S: number; W: number; E: number }

export interface Level { upper: number | null; label: string; color: string }

export interface GasDescriptor {
  key: string; formula: string; name: string; accent: string; product: string;
  unit: string; coverageStart: string; defaultHotspots: number;
  statSuffix: string; enhancementKey: string; headlinePct: boolean;
  hasCompare: boolean; digits: number; statDigits: number; axisTitle: string;
  palette: string[]; hotspotColor: string; colorbarCaption: string;
  levels: Level[]; levelUnit: string; levelTitle: string;
  noiseNote: string | null;
}

export interface DashboardCard {
  key: string; formula: string; name: string; accent: string; product: string;
  unit: string; since: string; sdgs: string[]; tellsYou: string;
  inCombination: string; live: boolean;
}

export interface MapBox {
  bbox: BBox; color: string; tooltip: string; weight: number;
  fillOpacity: number; dash: string | null; badge: string | null;
}

export interface MapLine {
  coords: [number, number][]; color: string; weight: number; opacity: number;
}

export interface MapDescriptor {
  fit: BBox;
  tiles: { url: string; name: string; opacity: number; show: boolean }[];
  boxes: MapBox[];
  hotspotBoxes?: MapBox[];
  lines: MapLine[];
  colorbar: { colors: string[]; vmin: number; vmax: number; caption: string } | null;
  classLegend?: {
    title: string; note: string;
    classes: { low: number; high: number | null; color: string }[];
  };
  hotspotLayerName?: string;
}

export type VegaSpec = Record<string, unknown> | null

export interface GasRun {
  error: string | null;
  label?: string;
  result?: Record<string, any>;
  charts?: Record<string, VegaSpec>;
  map?: MapDescriptor;
  levelLegend?: string;
}

export interface Location {
  region_name?: string | null; city_name?: string | null;
  N?: number | null; S?: number | null; W?: number | null; E?: number | null;
}

export interface Query extends Location { date_start: string; date_end: string }

export interface Co2Config {
  sources: Record<string, {
    label: string; unit: string; cadence: string; kind: string;
    coverage: [string, string]; whatItIs: string;
  }>;
  levels: Level[]; levelUnit: string; levelTitle: string; accent: string;
  no2CoverageStart: string; emissionRatios: Record<string, number>;
  prose: Record<string, string>;
}

// `available: false` means `reason`/`detail` are the tab's content, not an error.
export interface Co2Result {
  available: boolean;
  reason?: string; detail?: string;
  adequacy?: { cells: number; cell_km: [number, number]; suggestion: string };
  charts?: Record<string, VegaSpec>;
  map?: MapDescriptor | null;
  prose?: Record<string, string>;
  [key: string]: any;
}
