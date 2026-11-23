import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

type Props = {
  lon: number;
  lat: number;
  geometry: { type: string; coordinates: unknown } | null | undefined;
  geometryKind: string;
};

export function MapPane({ lon, lat, geometry, geometryKind }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      style: "https://tiles.openfreemap.org/styles/positron",
      center: [lon, lat],
      zoom: 16,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      if (geometry && geometry.type !== "Point") {
        map.addSource("parcel", {
          type: "geojson",
          data: {
            type: "Feature",
            properties: {},
            geometry: geometry as never,
          },
        });
        map.addLayer({
          id: "parcel-fill",
          type: "fill",
          source: "parcel",
          paint: { "fill-color": "#0f5f5a", "fill-opacity": 0.18 },
        });
        map.addLayer({
          id: "parcel-line",
          type: "line",
          source: "parcel",
          paint: { "line-color": "#0f5f5a", "line-width": 2 },
        });
        const bounds = new maplibregl.LngLatBounds();
        const walk = (value: unknown) => {
          if (!Array.isArray(value)) return;
          if (typeof value[0] === "number" && typeof value[1] === "number") {
            bounds.extend([value[0], value[1]]);
            return;
          }
          value.forEach(walk);
        };
        walk(geometry.coordinates);
        if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 36, maxZoom: 17 });
      }
      new maplibregl.Marker({ color: "#1b1916" }).setLngLat([lon, lat]).addTo(map);
    });
    return () => map.remove();
  }, [lon, lat, geometry, geometryKind]);

  return <div ref={ref} className="map" role="img" aria-label="Property map" />;
}
