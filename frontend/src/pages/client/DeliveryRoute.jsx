import { useEffect, useState } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { RefreshCw, Truck } from "lucide-react";
import { api, money } from "../../api";
import Status from "../../components/shared/Status";

// Fix default marker icons (Webpack strips them by default).
const icon = new L.DivIcon({
  className: "route-pin",
  html: '<div class="route-pin-dot"></div>',
  iconSize: [22, 22], iconAnchor: [11, 11],
});

function Fit({ orders, center }) {
  const map = useMap();
  useEffect(() => {
    if (orders.length === 0) { map.setView([center.lat, center.lng], 12); return; }
    const bounds = L.latLngBounds(orders.map((o) => [o.lat, o.lng]));
    map.fitBounds(bounds, { padding: [40, 40] });
  }, [orders, center, map]);
  return null;
}

export default function DeliveryRoute() {
  const [data, setData] = useState({ orders: [], center: { lat: 13.0827, lng: 80.2707 }, city: "Chennai" });
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    api.get("/workspace/delivery-route").then((r) => setData(r.data)).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  return (
    <section className="content">
      <div className="page-heading">
        <div>
          <div className="eyebrow">DELIVERY ROUTE</div>
          <h1>Rider handoff sequence</h1>
          <p>Today's home-delivery orders, sorted for a smooth south-to-north route in {data.city}.</p>
        </div>
        <button className="secondary-button" onClick={load} data-testid="refresh-route-button"><RefreshCw size={15} /> {loading ? "Refreshing…" : "Refresh"}</button>
      </div>
      <div className="route-grid">
        <div className="panel route-map-wrap" data-testid="delivery-map">
          <MapContainer center={[data.center.lat, data.center.lng]} zoom={12} style={{ height: 480, width: "100%" }}>
            <TileLayer attribution="© OpenStreetMap" url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" />
            <Fit orders={data.orders} center={data.center} />
            {data.orders.map((o, i) => (
              <Marker key={o.id} position={[o.lat, o.lng]} icon={icon}>
                <Popup>
                  <b>#{i + 1} · {o.id}</b><br />
                  {o.customer}<br />
                  <small>{o.address}</small><br />
                  <b>{money(o.total)}</b>
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        </div>
        <div className="panel route-list">
          <div className="panel-head"><div><h2>Route order</h2><p>{data.orders.length} deliveries queued</p></div></div>
          {data.orders.length === 0 && <div className="empty-inline">No live deliveries. Pack an order and it will appear here.</div>}
          {data.orders.map((o, i) => (
            <div className="route-stop" key={o.id} data-testid={`route-stop-${o.id}`}>
              <div className="route-index">{i + 1}</div>
              <div>
                <b className="mono">{o.id}</b>
                <small><Truck size={12} /> {o.customer} · {money(o.total)}</small>
                <small className="route-address">{o.address}</small>
              </div>
              <Status tone={o.status === "OUT_FOR_DELIVERY" ? "green" : "orange"}>{o.status.replaceAll("_", " ")}</Status>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
