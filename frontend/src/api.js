import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
export const api = axios.create({ withCredentials: true, baseURL: API });
export const money = (v) => `₹${Number(v || 0).toLocaleString("en-IN")}`;
export const humanStatus = (s) => (s || "").replaceAll("_", " ");

export const statusTone = (s) => {
  if (["COMPLETED", "DELIVERED", "COLLECTED"].includes(s)) return "green";
  if (["OUT_FOR_DELIVERY", "READY_FOR_PICKUP", "READY_FOR_DISPATCH"].includes(s)) return "blue";
  if (["NEW"].includes(s)) return "red";
  if (["CANCELLED"].includes(s)) return "neutral";
  return "orange";
};

export const nextStep = (order) => {
  const s = order.status;
  const isPickup = order.fulfilment === "STORE_PICKUP";
  const map = {
    NEW: "PICKING",
    PICKING: "PACKING",
    PACKING: isPickup ? "READY_FOR_PICKUP" : "READY_FOR_DISPATCH",
    READY_FOR_DISPATCH: "OUT_FOR_DELIVERY",
    READY_FOR_PICKUP: "COLLECTED",
    OUT_FOR_DELIVERY: "DELIVERED",
    DELIVERED: "COMPLETED",
    COLLECTED: "COMPLETED",
  };
  return map[s] || null;
};

export const nextLabel = (order) => {
  const n = nextStep(order);
  if (!n) return null;
  const labels = {
    PICKING: "Start picking",
    PACKING: "Move to packing",
    READY_FOR_PICKUP: "Mark ready for pickup",
    READY_FOR_DISPATCH: "Mark ready for dispatch",
    OUT_FOR_DELIVERY: "Send out for delivery",
    DELIVERED: "Mark delivered",
    COLLECTED: "Mark collected",
    COMPLETED: "Complete order",
  };
  return { status: n, label: labels[n] };
};
