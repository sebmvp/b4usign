import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

type Props = {
  lon: number;
  lat: number;
  geometry: { type: string; coordinates: unknown } | null | undefined;
  geometryKind: string;
  sheet?: boolean;
};

const IMAGERY = {
  version: 8 as const,
  sources: {
    imagery: {
      type: "raster" as const,
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      attribution: "Esri, Maxar, Earthstar Geographics",
    },
  },
  layers: [{ id: "imagery", type: "raster" as const, source: "imagery" }],
};

function easeOut(t: number) {
  return 1 - Math.pow(1 - t, 3);
}

export function MapPane({ lon, lat, geometry, geometryKind, sheet = false }: Props) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const map = new maplibregl.Map({
      container: ref.current,
      style: IMAGERY,
      center: [lon, lat],
      zoom: 17,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");

    map.on("load", () => {
      const wide = sheet && window.innerWidth > 860;
      const padding = { top: 48, bottom: 36, left: 36, right: wide ? 300 : 36 };
      const hasShape = Boolean(geometry && geometry.type !== "Point");
      if (hasShape && geometry) {
        map.addSource("parcel", {
          type: "geojson",
          data: { type: "Feature", properties: {}, geometry: geometry as never },
        });
        map.addLayer({
          id: "parcel-fill",
          type: "fill",
          source: "parcel",
          paint: { "fill-color": "#f3c15a", "fill-opacity": reduce ? 0.22 : 0 },
        });
        map.addLayer({
          id: "parcel-line",
          type: "line",
          source: "parcel",
          paint: {
            "line-color": "#f3c15a",
            "line-width": 2.5,
            "line-opacity": reduce ? 1 : 0,
          },
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
        if (!bounds.isEmpty()) map.fitBounds(bounds, { padding, maxZoom: 18, duration: reduce ? 0 : 700 });
        if (!reduce) {
          const start = performance.now();
          const tick = (now: number) => {
            const t = Math.min(1, (now - start) / 700);
            const eased = easeOut(t);
            map.setPaintProperty("parcel-fill", "fill-opacity", 0.22 * eased);
            map.setPaintProperty("parcel-line", "line-opacity", eased);
            if (t < 1) requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
        }
      } else {
        map.easeTo({ center: [lon, lat], zoom: 18, padding, duration: reduce ? 0 : 600 });
      }
      const dot = document.createElement("div");
      dot.className = "map-dot";
      dot.title = geometryKind === "parent_parcel" ? "Property-appraiser point. The line is the parent parcel." : "Property-appraiser point.";
      new maplibregl.Marker({ element: dot }).setLngLat([lon, lat]).addTo(map);
    });
    return () => map.remove();
  }, [lon, lat, geometry, geometryKind, sheet]);

  return <div ref={ref} className="map" role="img" aria-label="Property aerial photograph" />;
}
