import axios from 'axios'
import { toast } from 'sonner'

const apiClient = axios.create({
  baseURL: '',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

apiClient.interceptors.request.use((config) => {
  try {
    const token = localStorage.getItem('wagglebot-token')
    if (token) config.headers.Authorization = `Bearer ${token}`
  } catch {}
  return config
})

apiClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      try { localStorage.removeItem('wagglebot-token') } catch {}
      toast.error('인증이 만료되었습니다')
    } else if (err.response?.status >= 500) {
      toast.error(`서버 오류: ${err.response?.data?.error ?? '알 수 없는 오류'}`)
    }
    return Promise.reject(err)
  }
)

export default apiClient

export async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const res = await apiClient.get<T>(url, { params })
  return res.data
}

export async function post<T>(url: string, data?: unknown): Promise<T> {
  const res = await apiClient.post<T>(url, data)
  return res.data
}

export async function put<T>(url: string, data?: unknown): Promise<T> {
  const res = await apiClient.put<T>(url, data)
  return res.data
}

export async function del<T>(url: string): Promise<T> {
  const res = await apiClient.delete<T>(url)
  return res.data
}
