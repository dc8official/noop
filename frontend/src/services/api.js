import axios from 'axios'
import { clearUserState } from './auth.js'

const api = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      clearUserState()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api

export function getVersion() {
  return api.get('/version')
}

export function getEndpoints(status = null) {
  const params = {}
  if (status) params.status = status
  return api.get('/endpoints/', { params })
}

export function getEndpoint(id) {
  return api.get(`/endpoints/${id}`)
}

export function getTopology() {
  return api.get('/topology')
}

export function getEndpointTraces(id) {
  return api.get(`/endpoints/${id}/traces`)
}

export function getEndpointRca(id) {
  return api.get(`/endpoints/${id}/rca`)
}

export function refreshEndpointBaseline(id) {
  return api.post(`/endpoints/${id}/refresh-baseline`)
}

export function getUptimeReport(id, startDate, endDate) {
  return api.get(`/reports/uptime/${id}`, {
    params: {
      start_date: startDate,
      end_date: endDate,
    },
  })
}

export function getEndpointEvents(id, startDate, endDate, page = 1, pageSize = 50) {
  return api.get(`/reports/events/${id}`, {
    params: {
      start_date: startDate,
      end_date: endDate,
      page,
      page_size: pageSize,
    },
  })
}

export function getAvailabilityReport(id, startDate, endDate) {
  return api.get(`/reports/availability/${id}`, {
    params: {
      start_date: startDate,
      end_date: endDate,
    },
  })
}

export function getRttTrend(id, startDate, endDate) {
  return api.get(`/reports/rtt-trend/${id}`, {
    params: {
      start_date: startDate,
      end_date: endDate,
    },
  })
}

export function getTransitionTimeline(id, startDate, endDate) {
  return api.get(`/reports/timeline/${id}`, {
    params: {
      start_date: startDate,
      end_date: endDate,
    },
  })
}

export function getAuditLogs(params = {}) {
  return api.get('/reports/audit-logs', { params })
}

export function exportBatchTelemetry(endpointIds, startTime, endTime, columns = null) {
  const payload = {
    endpoint_ids: endpointIds,
    start_time: startTime,
    end_time: endTime,
  }
  if (columns && columns.length > 0) {
    payload.columns = columns
  }
  return api.post(
    '/telemetry/export/batch',
    payload,
    {
      responseType: 'blob',
    }
  )
}

export function exportTelemetryCsv(endpointId, startDate, endDate) {
  return api.get(`/reports/telemetry/export/${endpointId}`, {
    params: {
      start_date: startDate,
      end_date: endDate,
    },
    responseType: 'blob',
  })
}

export function login(username, password) {
  return api.post('/auth/login', { username, password })
}

export function logout() {
  return api.post('/auth/logout')
}

export function createEndpoint(data) {
  return api.post('/endpoints/', data)
}

export function updateEndpoint(id, data) {
  return api.patch(`/endpoints/${id}`, data)
}

export function deleteEndpoint(id) {
  return api.delete(`/endpoints/${id}`)
}

export function changePassword(data) {
  return api.post('/auth/change-password', data)
}

export function getUsers() {
  return api.get('/users/')
}

export function createUser(data) {
  return api.post('/users/', data)
}

export function resetUserPassword(userId, data) {
  return api.post(`/users/${userId}/reset-password`, data)
}

export function updateUser(userId, data) {
  return api.patch(`/users/${userId}`, data)
}

export function deleteUser(userId) {
  return api.delete(`/users/${userId}`)
}

export function getFleetSummary(startDate, endDate) {
  return api.get('/reports/fleet-summary', {
    params: {
      start_date: startDate,
      end_date: endDate,
    },
  })
}

export function getSettings() {
  return api.get('/settings')
}

export function updateSettings(data) {
  return api.patch('/settings', data)
}

export function getAlertChannels() {
  return api.get('/alerts/channels')
}

export function createAlertChannel(data) {
  return api.post('/alerts/channels', data)
}

export function getAlertChannel(id) {
  return api.get(`/alerts/channels/${id}`)
}

export function updateAlertChannel(id, data) {
  return api.put(`/alerts/channels/${id}`, data)
}

export function deleteAlertChannel(id) {
  return api.delete(`/alerts/channels/${id}`)
}

export function testAlertChannel(data) {
  return api.post('/alerts/channels/test', data)
}

export function getAlertHistory(page = 1, pageSize = 50) {
  return api.get('/alerts/history', {
    params: {
      page,
      page_size: pageSize,
    },
  })
}

