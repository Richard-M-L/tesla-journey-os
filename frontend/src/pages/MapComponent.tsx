import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import type { TripSummary } from "@/types";
import "leaflet/dist/leaflet.css";

// Use a simple colored circle marker — no external PNG assets required
const circleIcon = new L.DivIcon({
  className: "",
  html: '<div style="width:12px;height:12px;border-radius:50%;background:#3E6AE1;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,0.4)"></div>',
  iconSize: [12, 12],
  iconAnchor: [6, 6],
  popupAnchor: [0, -8],
});

interface Props {
  trips: TripSummary[];
}

export default function MapComponent({ trips }: Props) {
  const points: [number, number][] = [];
  for (const trip of trips) {
    if (trip.start_lat && trip.start_lon) points.push([trip.start_lat, trip.start_lon]);
    if (trip.end_lat && trip.end_lon) points.push([trip.end_lat, trip.end_lon]);
  }

  const center: [number, number] = points.length > 0
    ? [points.reduce((s, p) => s + p[0], 0) / points.length,
       points.reduce((s, p) => s + p[1], 0) / points.length]
    : [31.23, 121.47]; // Default: Shanghai

  return (
    <MapContainer
      center={center}
      zoom={11}
      style={{ height: "100%", width: "100%" }}
      attributionControl={true}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {trips.map((trip) => {
        if (!trip.start_lat || !trip.start_lon) return null;
        return (
          <Marker key={`start-${trip.id}`} position={[trip.start_lat, trip.start_lon]} icon={circleIcon}>
            <Popup>
              <div className="text-sm">
                <p className="font-semibold">行程 #{trip.id}</p>
                <p className="text-gray-500">{trip.distance_km.toFixed(1)} km</p>
              </div>
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
