import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8003",
  timeout: 13000,
});

export function getHealth() {
  return api.get("/health");
}

export default api;
