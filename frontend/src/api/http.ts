import axios from "axios"

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api/v1",
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message = error.response?.data?.message || error.message || "请求失败"
    console.error("API Error:", message)
    return Promise.reject(error)
  },
)

export default http
