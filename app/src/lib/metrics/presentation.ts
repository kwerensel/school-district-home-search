export type MapMetricKey =
  | "purchasingPower"
  | "treeCanopy"
  | "floodExposure"
  | "lightPollution"
  | "walkability"
  | "risk"
  | "parkAccess"
  | "transitAccess"
  | "commuteMinutes"
  | "airQuality"
  | "transportationNoise"
  | "sirenSources"
  | "nightlifeSources"
  | "industrialLand"
  | "freightRail";

export type ExplorerMapMetricKey =
  | "schoolDistricts"
  | Exclude<
      MapMetricKey,
      | "purchasingPower"
      | "transitAccess"
      | "commuteMinutes"
      | "airQuality"
      | "transportationNoise"
      | "sirenSources"
      | "nightlifeSources"
      | "industrialLand"
      | "freightRail"
    >;

export type MetricScale = {
  label: string;
  shortLabel: string;
  lowLabel: string;
  highLabel: string;
  colors: readonly string[];
};

export const MAP_METRIC_SCALES: Record<MapMetricKey, MetricScale> = {
  purchasingPower: {
    label: "Purchasing power",
    shortLabel: "Max home price",
    lowLabel: "Lower max price",
    highLabel: "Higher max price",
    colors: ["#b91c1c", "#f97316", "#eab308", "#22c55e", "#0284c7"],
  },
  treeCanopy: {
    label: "Tree coverage",
    shortLabel: "Tree coverage",
    lowLabel: "Sparse",
    highLabel: "Very leafy",
    colors: ["#f5e6c8", "#c7d99b", "#79b86b", "#2f855a", "#14532d"],
  },
  floodExposure: {
    label: "FEMA flood exposure",
    shortLabel: "Flood-zone land",
    lowLabel: "Less exposed",
    highLabel: "More exposed",
    colors: ["#ecfdf5", "#a7f3d0", "#67e8f9", "#38bdf8", "#0369a1"],
  },
  lightPollution: {
    label: "Light pollution",
    shortLabel: "Light pollution",
    lowLabel: "Darker",
    highLabel: "Brighter",
    colors: ["#24104f", "#4c1d95", "#7c3aed", "#f59e0b", "#fde047"],
  },
  walkability: {
    label: "EPA walkability",
    shortLabel: "EPA walkability",
    lowLabel: "Less walkable",
    highLabel: "More walkable",
    colors: ["#fff7ed", "#fed7aa", "#fdba74", "#4ade80", "#15803d"],
  },
  risk: {
    label: "Natural-hazard risk",
    shortLabel: "Hazard risk",
    lowLabel: "Lower risk",
    highLabel: "Higher risk",
    colors: ["#dcfce7", "#86efac", "#fde047", "#fb923c", "#dc2626"],
  },
  parkAccess: {
    label: "Park access",
    shortLabel: "Park access",
    lowLabel: "Less access",
    highLabel: "More access",
    colors: ["#f7fee7", "#d9f99d", "#86efac", "#22c55e", "#166534"],
  },
  transitAccess: {
    label: "Transit-stop density",
    shortLabel: "Transit stops / km²",
    lowLabel: "Fewer mapped stops",
    highLabel: "More mapped stops",
    colors: ["#f8fafc", "#cbd5e1", "#93c5fd", "#3b82f6", "#1e3a8a"],
  },
  commuteMinutes: {
    label: "Drive time to city anchor",
    shortLabel: "Drive time",
    lowLabel: "Shorter drive",
    highLabel: "Longer drive",
    colors: ["#dcfce7", "#86efac", "#fde047", "#fb923c", "#dc2626"],
  },
  airQuality: {
    label: "Annual mean daily AQI",
    shortLabel: "Annual mean AQI",
    lowLabel: "Lower annual mean",
    highLabel: "Higher annual mean",
    colors: ["#dcfce7", "#86efac", "#fde047", "#fb923c", "#dc2626"],
  },
  transportationNoise: {
    label: "Modeled transportation noise",
    shortLabel: "Area at or above 55 dBA",
    lowLabel: "Less exposed",
    highLabel: "More exposed",
    colors: ["#ecfdf5", "#a7f3d0", "#fde047", "#fb923c", "#dc2626"],
  },
  sirenSources: {
    label: "Mapped emergency-response facilities",
    shortLabel: "Facilities / km²",
    lowLabel: "Fewer mapped facilities",
    highLabel: "More mapped facilities",
    colors: ["#f8fafc", "#cbd5e1", "#fde68a", "#fb923c", "#dc2626"],
  },
  nightlifeSources: {
    label: "Mapped nightlife venues",
    shortLabel: "Venues / km²",
    lowLabel: "Fewer mapped venues",
    highLabel: "More mapped venues",
    colors: ["#f8fafc", "#ddd6fe", "#c084fc", "#9333ea", "#581c87"],
  },
  industrialLand: {
    label: "Mapped industrial land",
    shortLabel: "Industrial land share",
    lowLabel: "Lower mapped share",
    highLabel: "Higher mapped share",
    colors: ["#f8fafc", "#d6d3d1", "#a8a29e", "#78716c", "#44403c"],
  },
  freightRail: {
    label: "Active freight-capable rail",
    shortLabel: "Rail km / km²",
    lowLabel: "Less mapped rail",
    highLabel: "More mapped rail",
    colors: ["#f8fafc", "#bfdbfe", "#60a5fa", "#2563eb", "#1e3a8a"],
  },
};

export const EXPLORER_MAP_METRICS: Array<{ value: ExplorerMapMetricKey; label: string }> = [
  { value: "schoolDistricts", label: "School districts" },
  { value: "treeCanopy", label: MAP_METRIC_SCALES.treeCanopy.label },
  { value: "floodExposure", label: MAP_METRIC_SCALES.floodExposure.label },
  { value: "lightPollution", label: MAP_METRIC_SCALES.lightPollution.label },
  { value: "walkability", label: MAP_METRIC_SCALES.walkability.label },
  { value: "risk", label: MAP_METRIC_SCALES.risk.label },
  { value: "parkAccess", label: MAP_METRIC_SCALES.parkAccess.label },
];

export const DISCOVERY_MAP_METRICS: Array<{ value: MapMetricKey; label: string }> = [
  { value: "purchasingPower", label: MAP_METRIC_SCALES.purchasingPower.label },
  { value: "treeCanopy", label: MAP_METRIC_SCALES.treeCanopy.label },
  { value: "floodExposure", label: MAP_METRIC_SCALES.floodExposure.label },
  { value: "lightPollution", label: MAP_METRIC_SCALES.lightPollution.label },
  { value: "walkability", label: MAP_METRIC_SCALES.walkability.label },
  { value: "risk", label: MAP_METRIC_SCALES.risk.label },
  { value: "parkAccess", label: MAP_METRIC_SCALES.parkAccess.label },
  { value: "transitAccess", label: MAP_METRIC_SCALES.transitAccess.label },
  { value: "commuteMinutes", label: MAP_METRIC_SCALES.commuteMinutes.label },
  { value: "airQuality", label: MAP_METRIC_SCALES.airQuality.label },
  { value: "transportationNoise", label: MAP_METRIC_SCALES.transportationNoise.label },
  { value: "sirenSources", label: MAP_METRIC_SCALES.sirenSources.label },
  { value: "nightlifeSources", label: MAP_METRIC_SCALES.nightlifeSources.label },
  { value: "industrialLand", label: MAP_METRIC_SCALES.industrialLand.label },
  { value: "freightRail", label: MAP_METRIC_SCALES.freightRail.label },
];

export function normalizedMetricPosition(
  metric: MapMetricKey,
  value: number,
  min: number,
  max: number,
) {
  if (!Number.isFinite(value) || min === max) return 0.5;
  if (
    metric === "lightPollution" ||
    metric === "sirenSources" ||
    metric === "nightlifeSources" ||
    metric === "freightRail"
  ) {
    const transformedValue = Math.log1p(Math.max(value, 0));
    const transformedMin = Math.log1p(Math.max(min, 0));
    const transformedMax = Math.log1p(Math.max(max, 0));
    return Math.min(
      Math.max((transformedValue - transformedMin) / (transformedMax - transformedMin), 0),
      1,
    );
  }
  return Math.min(Math.max((value - min) / (max - min), 0), 1);
}

export function colorForMetricValue(
  metric: MapMetricKey,
  value: number | null | undefined,
  min: number,
  max: number,
) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "#cbd5e1";
  const colors = MAP_METRIC_SCALES[metric].colors;
  const position = normalizedMetricPosition(metric, value, min, max);
  return colors[Math.min(Math.floor(position * colors.length), colors.length - 1)];
}

export function treeCoverCategory(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Unknown";
  if (value < 20) return "Sparse";
  if (value < 40) return "Some trees";
  if (value < 60) return "Leafy";
  return "Very leafy";
}

export function lightPollutionCategory(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Unknown";
  if (value <= 1) return "Very dark";
  if (value <= 5) return "Dark";
  if (value <= 15) return "Moderate glow";
  if (value <= 40) return "Bright";
  return "Very bright";
}

export function walkabilityCategory(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Unknown";
  if (value <= 5.75) return "Least walkable";
  if (value <= 10.5) return "Below average";
  if (value <= 15.25) return "Above average";
  return "Most walkable";
}

export function riskCategory(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "Unknown";
  if (value < 20) return "Very low";
  if (value < 40) return "Low";
  if (value < 60) return "Moderate";
  if (value < 80) return "High";
  return "Very high";
}

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const percent = new Intl.NumberFormat("en-US", {
  style: "percent",
  maximumFractionDigits: 1,
});

export function formatMapMetricValue(metric: MapMetricKey, value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "No data";
  if (metric === "purchasingPower") return currency.format(Math.round(value));
  if (metric === "treeCanopy") return `${treeCoverCategory(value)} · ${value.toFixed(0)}% coverage`;
  if (metric === "floodExposure") return `${percent.format(value)} of district land`;
  if (metric === "lightPollution") {
    return `${lightPollutionCategory(value)} · ${value.toFixed(1)} radiance`;
  }
  if (metric === "walkability") return `${walkabilityCategory(value)} · ${value.toFixed(1)} / 20`;
  if (metric === "parkAccess") return `${percent.format(value)} of district land within 800 m`;
  if (metric === "transitAccess") return `${value.toFixed(1)} mapped stops / km²`;
  if (metric === "commuteMinutes") return `${value.toFixed(0)} min by car`;
  if (metric === "airQuality") return `${value.toFixed(0)} annual mean daily AQI`;
  if (metric === "transportationNoise") return `${value.toFixed(1)}% at or above 55 dBA`;
  if (metric === "sirenSources") return `${value.toFixed(2)} mapped facilities / km²`;
  if (metric === "nightlifeSources") return `${value.toFixed(2)} mapped venues / km²`;
  if (metric === "industrialLand") return `${value.toFixed(1)}% mapped industrial land`;
  if (metric === "freightRail") return `${value.toFixed(2)} rail km / km²`;
  return `${riskCategory(value)} · ${value.toFixed(1)} / 100`;
}
