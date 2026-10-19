import { MetricExplainer } from "./MetricExplainer";

export function GreennessExplainer({ divergence = false }: { divergence?: boolean }) {
  return divergence ? (
    <MetricExplainer
      compact
      label="How the greenness gap works"
      title="Canopy / street-greenness gap"
    >
      <p>
        Tree-canopy percentile minus street-adjacent satellite-greenness percentile, in percentile
        points. Both ranks compare places in the same project region at the same grain using their
        latest promoted values. Positive means canopy ranks higher; negative means satellite street
        greenness ranks higher.
      </p>
      <p>
        This is a derived comparison, not a measured visibility gap. Satellite NDVI includes grass
        and other vegetation; it does not measure eye-level greenery or sidewalk shade.
      </p>
    </MetricExplainer>
  ) : (
    <MetricExplainer
      compact
      label="How satellite greenness works"
      title="Street-adjacent greenness (satellite)"
    >
      <p>
        Summer Sentinel-2 satellite NDVI estimates vegetation within 50 m of mapped OpenStreetMap
        roads. Higher values indicate more green vegetation. Cloud-masked observations are combined
        into a seasonal median before averaging the stated tract or listing buffer.
      </p>
      <p>
        This satellite estimate is not photographic or eye-level GVI. It includes grass and shrubs
        as well as trees, and cannot confirm parcel greenery, street visibility, or sidewalk shade.
      </p>
    </MetricExplainer>
  );
}
