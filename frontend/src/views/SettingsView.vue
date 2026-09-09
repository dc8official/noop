<template>
  <div class="settings-view">
    <!-- Header Toolbar -->
    <div class="view-header">
      <div>
        <h1 class="page-title">Platform Administration & Governance</h1>
        <p class="page-sub">Configure enterprise alerting channels, performance acceleration, security policies, and access control</p>
      </div>
      <div class="header-actions">
        <button 
          v-if="activeTab !== 'alerts'" 
          class="btn-primary" 
          @click="saveAllSettings" 
          :disabled="saving"
        >
          {{ saving ? 'Saving...' : '💾 Save Settings' }}
        </button>
      </div>
    </div>

    <!-- Alert / Toast Banner -->
    <div v-if="alertMessage" :class="['alert-banner', alertType]">
      <span>{{ alertMessage }}</span>
      <button class="btn-close" @click="alertMessage = null">✕</button>
    </div>

    <!-- Spacious 4-Tab Navigation Strip -->
    <div class="settings-tabs-nav" role="tablist">
      <button 
        type="button" 
        class="tab-btn" 
        :class="{ active: activeTab === 'alerts' }" 
        @click="activeTab = 'alerts'"
        role="tab"
      >
        <span class="tab-icon">🔔</span>
        <span class="tab-label">Alert Channels</span>
        <span class="tab-count" v-if="channels.length > 0">{{ channels.length }}</span>
      </button>

      <button 
        type="button" 
        class="tab-btn" 
        :class="{ active: activeTab === 'performance' }" 
        @click="activeTab = 'performance'"
        role="tab"
      >
        <span class="tab-icon">⚡</span>
        <span class="tab-label">Performance & Storage</span>
      </button>

      <button 
        type="button" 
        class="tab-btn" 
        :class="{ active: activeTab === 'security' }" 
        @click="activeTab = 'security'"
        role="tab"
      >
        <span class="tab-icon">🛡️</span>
        <span class="tab-label">Security & Discovery</span>
      </button>

      <button 
        type="button" 
        class="tab-btn" 
        :class="{ active: activeTab === 'users' }" 
        @click="activeTab = 'users'"
        role="tab"
      >
        <span class="tab-icon">👥</span>
        <span class="tab-label">User Governance</span>
        <span class="tab-count" v-if="users.length > 0">{{ users.length }}</span>
      </button>
    </div>

    <!-- TAB 1: Enterprise Alert Channels -->
    <div v-if="activeTab === 'alerts'" class="tab-pane">
      <!-- Master Engine Switch Card -->
      <div class="settings-card mb-4">
        <div class="card-header">
          <div class="flex-1">
            <div class="flex-row-center gap-2">
              <h2 class="card-title">🚨 Enterprise Alerting & Notification Engine</h2>
              <span class="engine-badge" :class="settings.alertingEnabled ? 'badge-redis' : 'badge-pg'">
                {{ settings.alertingEnabled ? 'DISPATCHER ACTIVE' : 'DISPATCHER PAUSED' }}
              </span>
            </div>
            <p class="card-desc mt-1">
              Evaluates real-time state transitions and dispatches notifications to Microsoft Teams, Discord, Slack, SMTP Email, or Generic Webhooks.
              All dispatching runs asynchronously inside background workers, completely decoupled with zero impact on the 32-second ICMP probing sweep.
            </p>
          </div>
          <div class="master-toggle-wrap">
            <label class="switch">
              <input type="checkbox" v-model="settings.alertingEnabled" @change="saveAllSettings" />
              <span class="slider round"></span>
            </label>
          </div>
        </div>
      </div>

      <!-- Configured Alert Channels Table -->
      <div class="settings-card full-width mb-4">
        <div class="card-header">
          <div>
            <h2 class="card-title">Configured Notification Channels</h2>
            <p class="card-desc">Active delivery targets for telemetry transitions, latency degradation, and downtime events.</p>
          </div>
          <button class="btn-primary" @click="openAddChannelModal">
            + Add Alert Channel
          </button>
        </div>

        <div class="table-responsive" style="margin-top: 14px;">
          <table class="data-table" aria-label="Alert Channels Table">
            <thead>
              <tr>
                <th>Channel Name</th>
                <th>Provider</th>
                <th>Endpoint Scope</th>
                <th>Severities</th>
                <th>Status</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="channelsLoading">
                <td colspan="6" class="text-center py-6 text-muted">Loading configured notification channels...</td>
              </tr>
              <tr v-else-if="channels.length === 0">
                <td colspan="6" class="text-center py-6 text-muted">
                  No alert channels configured. Click <strong>+ Add Alert Channel</strong> to route alerts to Teams, Discord, Slack, or Email.
                </td>
              </tr>
              <tr v-for="ch in channels" :key="ch.id">
                <td class="font-bold">{{ ch.name }}</td>
                <td>
                  <span class="provider-pill" :class="ch.channel_type.toLowerCase()">
                    {{ formatProviderName(ch.channel_type) }}
                  </span>
                </td>
                <td>
                  <span v-if="!ch.endpoint_ids || ch.endpoint_ids.length === 0" class="badge-scope all">
                    All Monitored Nodes
                  </span>
                  <span v-else class="badge-scope custom">
                    {{ ch.endpoint_ids.length }} Specific Node(s)
                  </span>
                </td>
                <td>
                  <div class="severity-tag-group">
                    <span 
                      v-for="s in (ch.severity_filters || ['DOWN', 'RECOVERED'])" 
                      :key="s" 
                      class="severity-tag"
                      :class="s.toLowerCase()"
                    >
                      {{ s }}
                    </span>
                  </div>
                </td>
                <td>
                  <span class="status-pill" :class="ch.is_enabled ? 'status-up' : 'status-down'">
                    {{ ch.is_enabled ? 'ACTIVE' : 'PAUSED' }}
                  </span>
                </td>
                <td class="text-right">
                  <div class="table-actions">
                    <button 
                      class="btn-action" 
                      @click="triggerChannelTest(ch)" 
                      :disabled="testingChannelId === ch.id"
                      title="Send Diagnostic Probe"
                    >
                      <i class="pi" :class="testingChannelId === ch.id ? 'pi-spin pi-spinner' : 'pi-send'"></i>
                      {{ testingChannelId === ch.id ? 'Testing...' : 'Test' }}
                    </button>
                    <button class="btn-action" @click="openEditChannelModal(ch)" title="Edit Channel">
                      ✏️ Edit
                    </button>
                    <button class="btn-action text-down" @click="confirmDeleteChannel(ch)" title="Delete Channel">
                      ✕
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Real-Time Delivery Audit Log -->
      <div class="settings-card full-width">
        <div class="card-header">
          <div>
            <h2 class="card-title">Real-Time Delivery Audit Log</h2>
            <p class="card-desc">Most recent 50 alert dispatch events, HTTP response codes, and rate limiting status.</p>
          </div>
          <button class="btn-action" @click="fetchAlertLogs">
            🔄 Refresh Log
          </button>
        </div>

        <div class="table-responsive" style="margin-top: 14px;">
          <table class="data-table" aria-label="Alert Delivery Audit Log Table">
            <thead>
              <tr>
                <th>Delivered At (UTC)</th>
                <th>Channel</th>
                <th>Target Endpoint</th>
                <th>Event Type</th>
                <th>Delivery Status</th>
                <th>Response / Error Details</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="logsLoading">
                <td colspan="6" class="text-center py-6 text-muted">Loading delivery audit logs...</td>
              </tr>
              <tr v-else-if="deliveryLogs.length === 0">
                <td colspan="6" class="text-center py-6 text-muted">No alert delivery events recorded yet.</td>
              </tr>
              <tr v-for="log in deliveryLogs" :key="log.id">
                <td class="font-mono tnum">{{ new Date(log.delivered_at).toISOString().replace('T', ' ').slice(0, 19) }}</td>
                <td class="font-bold">{{ log.channel_name }}</td>
                <td class="font-mono">{{ log.endpoint_name }}</td>
                <td>
                  <span class="badge-scope">{{ log.event_type }}</span>
                </td>
                <td>
                  <span class="status-pill" :class="getDeliveryStatusClass(log.status)">
                    {{ log.status }} {{ log.status_code ? `(${log.status_code})` : '' }}
                  </span>
                </td>
                <td class="font-mono text-muted text-xs truncate-cell" :title="log.response_message || ''">
                  {{ log.response_message || 'OK' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 2: Performance & Storage -->
    <div v-if="activeTab === 'performance'" class="tab-pane">
      <div class="settings-card">
        <div class="card-header">
          <h2 class="card-title">⚡ Performance & Storage Engine</h2>
          <span class="engine-badge" :class="settings.performanceMode ? 'badge-redis' : 'badge-pg'">
            {{ settings.performanceMode ? 'REDIS ACCELERATED' : 'POSTGRESQL NATIVE' }}
          </span>
        </div>
        <p class="card-desc">
          Accelerate session lookups and real-time event broadcasting using in-memory Redis caching, with zero-downtime PostgreSQL fallback.
        </p>

        <div class="setting-row">
          <div>
            <label class="setting-label">Memory Acceleration Driver</label>
            <p class="setting-hint">When enabled, user session tokens and pub/sub events are routed through Redis.</p>
          </div>
          <div class="driver-toggle">
            <button 
              type="button" 
              class="btn-toggle-option" 
              :class="{ active: !settings.performanceMode }"
              @click="settings.performanceMode = false"
            >
              Standard (PostgreSQL)
            </button>
            <button 
              type="button" 
              class="btn-toggle-option" 
              :class="{ active: settings.performanceMode }"
              @click="settings.performanceMode = true"
            >
              Accelerated (Redis)
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: Security & Discovery -->
    <div v-if="activeTab === 'security'" class="tab-pane">
      <div class="settings-grid">
        <div class="settings-card">
          <div class="card-header">
            <h2 class="card-title">🌐 Network Discovery & Diagnostics</h2>
          </div>
          <p class="card-desc">Control automated traceroute behavior and subnet traversal optimization.</p>

          <div class="setting-row">
            <div>
              <label class="setting-label">Layer-2 Subnet Auto-Bypass</label>
              <p class="setting-hint">Automatically bypass ICMP/UDP traceroute subprocesses for hosts on the local /24 broadcast segment.</p>
            </div>
            <label class="switch">
              <input type="checkbox" v-model="settings.l2AutoBypass" />
              <span class="slider round"></span>
            </label>
          </div>

          <div class="setting-row">
            <div>
              <label class="setting-label">Max Concurrent Traces</label>
              <p class="setting-hint">Global concurrency semaphore bound for simultaneous diagnostic traceroutes.</p>
            </div>
            <span class="font-mono tnum font-bold">3 Traces (500ms pacing)</span>
          </div>
        </div>

        <div class="settings-card">
          <div class="card-header">
            <h2 class="card-title">🔒 Security & Access Policies</h2>
          </div>
          <p class="card-desc">Enforce session lifetime limits, brute-force throttling, and token revocation controls.</p>

          <div class="setting-row">
            <div>
              <label class="setting-label">User Session Inactivity Timeout</label>
              <p class="setting-hint">Automatic session revocation period for idle operator accounts.</p>
            </div>
            <select v-model="settings.sessionTimeout" class="form-select font-mono">
              <option value="15">15 Minutes</option>
              <option value="30">30 Minutes</option>
              <option value="60">1 Hour</option>
              <option value="120">2 Hours (Default)</option>
              <option value="240">4 Hours</option>
            </select>
          </div>

          <div class="setting-row">
            <div>
              <label class="setting-label">Brute-Force Lockout Threshold</label>
              <p class="setting-hint">Consecutive failed login attempts before IP and account cooldown is applied.</p>
            </div>
            <select v-model="settings.lockoutThreshold" class="form-select font-mono">
              <option value="3">3 Failed Attempts</option>
              <option value="5">5 Failed Attempts (Default)</option>
              <option value="10">10 Failed Attempts</option>
            </select>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 4: User Account Governance -->
    <div v-if="activeTab === 'users'" class="tab-pane">
      <div class="settings-card full-width">
        <div class="card-header">
          <div>
            <h2 class="card-title">👥 User Account Governance</h2>
            <p class="card-desc">Manage platform operator credentials, system access roles, and status.</p>
          </div>
          <button class="btn-primary btn-small" @click="openAddUserModal">
            + Add User Account
          </button>
        </div>

        <div class="table-responsive" style="margin-top: 12px;">
          <table class="data-table" aria-label="User Accounts Table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Role</th>
                <th>Status</th>
                <th>Credential State</th>
                <th>Last Active Sign-in</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="u in users" :key="u.id">
                <td class="font-bold">{{ u.username }}</td>
                <td>
                  <span class="role-badge" :class="u.role.toLowerCase()">
                    {{ u.role }}
                  </span>
                </td>
                <td>
                  <span class="status-pill" :class="u.is_active ? 'status-up' : 'status-down'">
                    {{ u.is_active ? 'ACTIVE' : 'DISABLED' }}
                  </span>
                </td>
                <td>
                  <span v-if="u.must_change_password" class="text-unstable font-bold">
                    ⚡ Reset Pending
                  </span>
                  <span v-else class="text-up font-bold">
                    ✓ Secure
                  </span>
                </td>
                <td class="font-mono tnum">
                  {{ u.last_login ? new Date(u.last_login).toLocaleString() : 'Never' }}
                </td>
                <td class="text-right">
                  <div class="table-actions">
                    <button class="btn-action" @click="openResetPasswordModal(u)" title="Reset Password">🔑 Reset</button>
                    <button 
                      v-if="u.username !== currentUser" 
                      class="btn-action" 
                      @click="toggleUserStatus(u)"
                    >
                      {{ u.is_active ? '🚫 Disable' : '✅ Enable' }}
                    </button>
                    <button 
                      v-if="u.username !== currentUser" 
                      class="btn-action text-down" 
                      @click="confirmDeleteUser(u)"
                    >
                      ✕
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 800px Channel Configuration Modal -->
    <div class="modal-overlay" v-if="showChannelModal" @click.self="showChannelModal = false">
      <div class="modal-card channel-modal-dialog">
        <div class="modal-header">
          <div>
            <h3 class="modal-title">{{ editingChannelId ? 'Edit Alert Channel' : 'Configure New Alert Channel' }}</h3>
            <p class="modal-subtitle">Configure outbound webhook or SMTP email notifications for real-time telemetry events.</p>
          </div>
          <button class="btn-close" @click="showChannelModal = false">✕</button>
        </div>

        <form @submit.prevent="saveChannel" class="modal-form">
          <!-- Provider Selection Cards -->
          <div class="form-group">
            <label class="setting-label">Select Notification Provider *</label>
            <div class="provider-selector-grid">
              <div 
                v-for="p in providerOptions" 
                :key="p.id" 
                class="provider-card" 
                :class="{ active: channelForm.channel_type === p.id }"
                @click="channelForm.channel_type = p.id"
              >
                <span class="provider-icon">{{ p.icon }}</span>
                <span class="provider-name">{{ p.name }}</span>
                <span class="provider-badge">{{ p.format }}</span>
              </div>
            </div>
          </div>

          <!-- Channel Name -->
          <div class="form-group">
            <label class="setting-label">Channel Display Name *</label>
            <input 
              v-model="channelForm.name" 
              type="text" 
              placeholder="e.g. NOC Critical Alerts / Team Chat" 
              required 
              class="form-input"
            />
          </div>

          <!-- Provider Specific Inputs -->
          <div v-if="channelForm.channel_type !== 'EMAIL_SMTP'" class="form-group">
            <label class="setting-label">
              Webhook Destination URL *
              <span class="label-hint">(Must be a valid HTTP/HTTPS endpoint. Private and loopback IPs are blocked by SSRF defense)</span>
            </label>
            <input 
              v-model="channelForm.config.webhook_url" 
              type="url" 
              :placeholder="getWebhookPlaceholder(channelForm.channel_type)" 
              required 
              class="form-input font-mono"
            />
          </div>

          <!-- Generic Webhook Headers -->
          <div v-if="channelForm.channel_type === 'GENERIC_WEBHOOK'" class="form-group">
            <label class="setting-label">Custom HTTP Headers (Optional JSON object)</label>
            <textarea 
              v-model="channelForm.headersRaw" 
              placeholder='{ "Authorization": "Bearer YOUR_TOKEN" }'
              rows="2"
              class="form-input font-mono"
            ></textarea>
          </div>

          <!-- SMTP Email Fields -->
          <div v-if="channelForm.channel_type === 'EMAIL_SMTP'" class="smtp-config-box">
            <div class="form-row-2">
              <div class="form-group">
                <label class="setting-label">SMTP Host *</label>
                <input v-model="channelForm.config.smtp_host" type="text" placeholder="smtp.office365.com" required class="form-input font-mono" />
              </div>
              <div class="form-group">
                <label class="setting-label">SMTP Port *</label>
                <input v-model.number="channelForm.config.smtp_port" type="number" placeholder="587" required class="form-input font-mono" />
              </div>
            </div>

            <div class="form-row-2">
              <div class="form-group">
                <label class="setting-label">SMTP Username</label>
                <input v-model="channelForm.config.username" type="text" placeholder="alerts@corp.net" class="form-input" />
              </div>
              <div class="form-group">
                <label class="setting-label">SMTP Password</label>
                <input v-model="channelForm.config.password" type="password" placeholder="••••••••••••" class="form-input" />
              </div>
            </div>

            <div class="form-row-2">
              <div class="form-group">
                <label class="setting-label">From Address *</label>
                <input v-model="channelForm.config.from_email" type="email" placeholder="lnmp-alerts@corp.net" required class="form-input" />
              </div>
              <div class="form-group">
                <label class="setting-label">Recipient Email(s) * (comma-separated)</label>
                <input v-model="channelForm.toEmailsRaw" type="text" placeholder="ops@corp.net, noc-oncall@corp.net" required class="form-input font-mono" />
              </div>
            </div>
          </div>

          <!-- Target Endpoint Scope -->
          <div class="form-group">
            <label class="setting-label">Target Endpoint Scope</label>
            <div class="radio-options mb-2">
              <label class="radio-label">
                <input type="radio" value="all" v-model="channelScope" />
                <span>All Monitored Endpoints (Entire Fleet)</span>
              </label>
              <label class="radio-label">
                <input type="radio" value="custom" v-model="channelScope" />
                <span>Specific Endpoints ({{ channelForm.endpoint_ids.length }} selected)</span>
              </label>
            </div>

            <div v-if="channelScope === 'custom'" class="target-picker-box">
              <div class="target-picker-header">
                <input 
                  type="text" 
                  v-model="endpointSearchFilter" 
                  placeholder="Filter targets by name or IP..." 
                  class="target-search-input"
                />
                <button type="button" class="btn-text-action" @click="toggleAllChannelEndpoints">
                  {{ isAllChannelEndpointsSelected ? 'Deselect All' : 'Select All' }}
                </button>
              </div>
              <div class="target-list">
                <div v-for="ep in filteredEndpoints" :key="ep.id" class="target-item">
                  <label class="checkbox-label">
                    <input type="checkbox" :value="ep.id" v-model="channelForm.endpoint_ids" />
                    <span class="target-name font-bold">{{ ep.hostname }}</span>
                    <span class="target-ip font-mono tnum">{{ ep.ip_address }}</span>
                    <span class="device-pill">{{ ep.device_type }}</span>
                  </label>
                </div>
              </div>
            </div>
          </div>

          <!-- Severity Filters -->
          <div class="form-group">
            <label class="setting-label">Triggering Severity States</label>
            <div class="severity-checkbox-group">
              <label class="checkbox-label">
                <input type="checkbox" value="DOWN" v-model="channelForm.severity_filters" />
                <span class="severity-tag down">DOWN</span>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" value="RECOVERED" v-model="channelForm.severity_filters" />
                <span class="severity-tag recovered">RECOVERED</span>
              </label>
              <label class="checkbox-label">
                <input type="checkbox" value="UNSTABLE" v-model="channelForm.severity_filters" />
                <span class="severity-tag unstable">UNSTABLE / FLAPPING</span>
              </label>
            </div>
          </div>

          <!-- Channel Active Toggle -->
          <div class="setting-row">
            <div>
              <label class="setting-label">Channel Status</label>
              <p class="setting-hint">Enable or pause outbound alerts for this channel.</p>
            </div>
            <label class="switch">
              <input type="checkbox" v-model="channelForm.is_enabled" />
              <span class="slider round"></span>
            </label>
          </div>

          <!-- Diagnostic Test Banner & Button -->
          <div class="diagnostic-test-section">
            <div v-if="modalTestResult" :class="['test-feedback-banner', modalTestResult.success ? 'success' : 'error']">
              <span>{{ modalTestResult.message }}</span>
            </div>

            <button 
              type="button" 
              class="btn-action" 
              @click="sendModalDiagnosticTest" 
              :disabled="modalTesting"
            >
              <i class="pi" :class="modalTesting ? 'pi-spin pi-spinner' : 'pi-send'"></i>
              <span>{{ modalTesting ? 'Sending Diagnostic Probe...' : '⚡ Send Diagnostic Test Alert' }}</span>
            </button>
          </div>

          <div class="modal-actions">
            <button type="button" class="btn-secondary" @click="showChannelModal = false">Cancel</button>
            <button type="submit" class="btn-primary" :disabled="channelSaving">
              {{ channelSaving ? 'Saving...' : (editingChannelId ? 'Update Channel' : 'Create Channel') }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Add User Modal -->
    <div class="modal-overlay" v-if="showAddModal" @click.self="showAddModal = false">
      <div class="modal-card">
        <div class="modal-header">
          <h3>Register New Operator Account</h3>
          <button class="btn-close" @click="showAddModal = false">✕</button>
        </div>
        <form @submit.prevent="saveNewUser" class="modal-form">
          <div class="form-group">
            <label>Username *</label>
            <input v-model="userForm.username" type="text" placeholder="operator_alex" required class="form-input" />
          </div>
          <div class="form-group">
            <label>Temporary Password</label>
            <input v-model="userForm.password" type="password" placeholder="Leave blank to auto-generate" class="form-input" />
          </div>
          <div class="form-group">
            <label>Account Role *</label>
            <select v-model="userForm.role" class="form-select">
              <option value="VIEWER">VIEWER (Read-Only Operator)</option>
              <option value="ADMIN">ADMIN (Full Administrative Control)</option>
            </select>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn-secondary" @click="showAddModal = false">Cancel</button>
            <button type="submit" class="btn-primary" :disabled="userSaving">
              {{ userSaving ? 'Creating...' : 'Register User' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- Reset Password Modal -->
    <div class="modal-overlay" v-if="showResetModal" @click.self="showResetModal = false">
      <div class="modal-card">
        <div class="modal-header">
          <h3>Reset Password for {{ targetUser?.username }}</h3>
          <button class="btn-close" @click="showResetModal = false">✕</button>
        </div>
        <form @submit.prevent="executeResetPassword" class="modal-form">
          <div class="form-group">
            <label>New Temporary Password</label>
            <input v-model="resetPasswordVal" type="password" placeholder="Leave blank to auto-generate" class="form-input" />
          </div>
          <div class="modal-actions">
            <button type="button" class="btn-secondary" @click="showResetModal = false">Cancel</button>
            <button type="submit" class="btn-primary" :disabled="userSaving">
              {{ userSaving ? 'Resetting...' : 'Confirm Reset' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  getUsers,
  createUser,
  resetUserPassword,
  updateUser,
  deleteUser,
  getSettings,
  updateSettings,
  getAlertChannels,
  createAlertChannel,
  updateAlertChannel,
  deleteAlertChannel,
  testAlertChannel,
  getAlertHistory,
  getEndpoints,
} from '../services/api.js'
import { currentUser, loadUserFromStorage } from '../services/auth.js'

const activeTab = ref('alerts')
const saving = ref(false)
const alertMessage = ref(null)
const alertType = ref('alert-success')

const settings = reactive({
  performanceMode: false,
  l2AutoBypass: true,
  sessionTimeout: '120',
  lockoutThreshold: '5',
  alertingEnabled: true,
})

// Alert Channels state
const channels = ref([])
const channelsLoading = ref(false)
const deliveryLogs = ref([])
const logsLoading = ref(false)
const testingChannelId = ref(null)

const showChannelModal = ref(false)
const editingChannelId = ref(null)
const channelSaving = ref(false)
const modalTesting = ref(false)
const modalTestResult = ref(null)
const channelScope = ref('all')
const endpointSearchFilter = ref('')
const endpoints = ref([])

const providerOptions = [
  { id: 'TEAMS', name: 'Microsoft Teams', format: 'Adaptive Card 1.4', icon: '🏢' },
  { id: 'DISCORD', name: 'Discord', format: 'Rich Embed', icon: '🎮' },
  { id: 'SLACK', name: 'Slack', format: 'Block Kit', icon: '💬' },
  { id: 'EMAIL_SMTP', name: 'Corporate Email', format: 'SMTP TLS 1.2+', icon: '✉️' },
  { id: 'GENERIC_WEBHOOK', name: 'Generic Webhook', format: 'JSON REST', icon: '🌐' },
]

const channelForm = reactive({
  name: '',
  channel_type: 'TEAMS',
  is_enabled: true,
  config: {
    webhook_url: '',
    smtp_host: '',
    smtp_port: 587,
    username: '',
    password: '',
    from_email: '',
  },
  headersRaw: '',
  toEmailsRaw: '',
  endpoint_ids: [],
  severity_filters: ['DOWN', 'RECOVERED'],
})

// Users state
const users = ref([])
const showAddModal = ref(false)
const showResetModal = ref(false)
const userSaving = ref(false)
const targetUser = ref(null)
const resetPasswordVal = ref('')

const userForm = reactive({
  username: '',
  password: '',
  role: 'VIEWER',
})

// Endpoints filtering
const filteredEndpoints = computed(() => {
  if (!endpointSearchFilter.value) return endpoints.value
  const q = endpointSearchFilter.value.toLowerCase()
  return endpoints.value.filter(e => 
    e.hostname.toLowerCase().includes(q) || e.ip_address.includes(q)
  )
})

const isAllChannelEndpointsSelected = computed(() => {
  return endpoints.value.length > 0 && channelForm.endpoint_ids.length === endpoints.value.length
})

function toggleAllChannelEndpoints() {
  if (isAllChannelEndpointsSelected.value) {
    channelForm.endpoint_ids = []
  } else {
    channelForm.endpoint_ids = endpoints.value.map(e => e.id)
  }
}

function formatProviderName(type) {
  const match = providerOptions.find(p => p.id === type)
  return match ? match.name : type
}

function getWebhookPlaceholder(type) {
  if (type === 'TEAMS') return 'https://outlook.office.com/webhook/...'
  if (type === 'DISCORD') return 'https://discord.com/api/webhooks/...'
  if (type === 'SLACK') return 'https://hooks.slack.com/services/...'
  return 'https://api.domain.corp/alerts/webhook'
}

function getDeliveryStatusClass(status) {
  const s = String(status).toUpperCase()
  if (s === 'DELIVERED') return 'status-up'
  if (s === 'FAILED') return 'status-down'
  return 'status-unstable'
}

async function fetchChannels() {
  channelsLoading.value = true
  try {
    const res = await getAlertChannels()
    channels.value = res.data?.data || []
  } catch (err) {
    console.error('Failed to load alert channels:', err)
  } finally {
    channelsLoading.value = false
  }
}

async function fetchAlertLogs() {
  logsLoading.value = true
  try {
    const res = await getAlertHistory(1, 50)
    deliveryLogs.value = res.data?.data || []
  } catch (err) {
    console.error('Failed to load delivery logs:', err)
  } finally {
    logsLoading.value = false
  }
}

async function fetchEndpointsList() {
  try {
    const res = await getEndpoints()
    endpoints.value = res.data?.data || []
  } catch (err) {
    console.error('Failed to load endpoints:', err)
  }
}

async function fetchUsersList() {
  try {
    const res = await getUsers()
    users.value = res.data?.data || []
  } catch (err) {
    console.error('Failed to load users:', err)
  }
}

async function loadSettings() {
  try {
    const res = await getSettings()
    const data = res.data?.data
    if (data) {
      if (data.performance_mode !== undefined) settings.performanceMode = data.performance_mode
      else if (data.performanceMode !== undefined) settings.performanceMode = data.performanceMode
      if (data.l2_auto_bypass !== undefined) settings.l2AutoBypass = data.l2_auto_bypass
      else if (data.l2AutoBypass !== undefined) settings.l2AutoBypass = data.l2AutoBypass
      if (data.session_timeout !== undefined) settings.sessionTimeout = String(data.session_timeout)
      else if (data.sessionTimeout !== undefined) settings.sessionTimeout = String(data.sessionTimeout)
      if (data.lockout_threshold !== undefined) settings.lockoutThreshold = String(data.lockout_threshold)
      else if (data.lockoutThreshold !== undefined) settings.lockoutThreshold = String(data.lockoutThreshold)
      if (data.alerting_enabled !== undefined) settings.alertingEnabled = data.alerting_enabled
      else if (data.alertingEnabled !== undefined) settings.alertingEnabled = data.alertingEnabled
    }
  } catch (err) {
    console.error('Failed to load settings:', err)
  }
}

async function saveAllSettings() {
  saving.value = true
  alertMessage.value = null
  try {
    await updateSettings({
      performance_mode: settings.performanceMode,
      l2_auto_bypass: settings.l2AutoBypass,
      session_timeout: parseInt(settings.sessionTimeout, 10),
      lockout_threshold: parseInt(settings.lockoutThreshold, 10),
      alerting_enabled: settings.alertingEnabled,
    })
    alertMessage.value = 'Platform governance and engine settings applied successfully.'
    alertType.value = 'alert-success'
  } catch (err) {
    alertMessage.value = err.response?.data?.detail || 'Failed to update platform settings.'
    alertType.value = 'alert-error'
  } finally {
    saving.value = false
  }
}

function openAddChannelModal() {
  editingChannelId.value = null
  channelForm.name = ''
  channelForm.channel_type = 'TEAMS'
  channelForm.is_enabled = true
  channelForm.config = {
    webhook_url: '',
    smtp_host: '',
    smtp_port: 587,
    username: '',
    password: '',
    from_email: '',
  }
  channelForm.headersRaw = ''
  channelForm.toEmailsRaw = ''
  channelForm.endpoint_ids = []
  channelForm.severity_filters = ['DOWN', 'RECOVERED']
  channelScope.value = 'all'
  modalTestResult.value = null
  showChannelModal.value = true
}

function openEditChannelModal(ch) {
  editingChannelId.value = ch.id
  channelForm.name = ch.name
  channelForm.channel_type = ch.channel_type
  channelForm.is_enabled = ch.is_enabled
  channelForm.config = { ...ch.config }
  channelForm.endpoint_ids = ch.endpoint_ids ? [...ch.endpoint_ids] : []
  channelForm.severity_filters = ch.severity_filters ? [...ch.severity_filters] : ['DOWN', 'RECOVERED']
  channelScope.value = (ch.endpoint_ids && ch.endpoint_ids.length > 0) ? 'custom' : 'all'

  if (ch.config?.headers) {
    channelForm.headersRaw = JSON.stringify(ch.config.headers, null, 2)
  } else {
    channelForm.headersRaw = ''
  }

  if (ch.config?.to_emails) {
    channelForm.toEmailsRaw = ch.config.to_emails.join(', ')
  } else {
    channelForm.toEmailsRaw = ''
  }

  modalTestResult.value = null
  showChannelModal.value = true
}

async function saveChannel() {
  channelSaving.value = true
  try {
    const payload = {
      name: channelForm.name,
      channel_type: channelForm.channel_type,
      is_enabled: channelForm.is_enabled,
      config: { ...channelForm.config },
      endpoint_ids: channelScope.value === 'all' ? [] : channelForm.endpoint_ids,
      severity_filters: channelForm.severity_filters,
    }

    if (channelForm.channel_type === 'GENERIC_WEBHOOK' && channelForm.headersRaw.trim()) {
      try {
        payload.config.headers = JSON.parse(channelForm.headersRaw)
      } catch (e) {
        alert('Invalid JSON in custom headers.')
        channelSaving.value = false
        return
      }
    }

    if (channelForm.channel_type === 'EMAIL_SMTP' && channelForm.toEmailsRaw.trim()) {
      payload.config.to_emails = channelForm.toEmailsRaw
        .split(',')
        .map(e => e.trim())
        .filter(Boolean)
    }

    if (editingChannelId.value) {
      await updateAlertChannel(editingChannelId.value, payload)
      alertMessage.value = `Alert channel '${channelForm.name}' updated.`
    } else {
      await createAlertChannel(payload)
      alertMessage.value = `Alert channel '${channelForm.name}' created.`
    }
    alertType.value = 'alert-success'
    showChannelModal.value = false
    await fetchChannels()
  } catch (err) {
    alertMessage.value = err.response?.data?.detail || 'Failed to save alert channel.'
    alertType.value = 'alert-error'
  } finally {
    channelSaving.value = false
  }
}

async function confirmDeleteChannel(ch) {
  if (!confirm(`Delete alert channel '${ch.name}'? Associated delivery history will also be removed.`)) return
  try {
    await deleteAlertChannel(ch.id)
    alertMessage.value = `Channel '${ch.name}' deleted.`
    alertType.value = 'alert-success'
    await fetchChannels()
  } catch (err) {
    alertMessage.value = err.response?.data?.detail || 'Failed to delete channel.'
    alertType.value = 'alert-error'
  }
}

async function triggerChannelTest(ch) {
  testingChannelId.value = ch.id
  try {
    const res = await testAlertChannel({ channel_id: ch.id })
    const data = res.data?.data
    if (data?.success) {
      alertMessage.value = `✓ Diagnostic test passed for '${ch.name}' (HTTP ${data.status_code}).`
      alertType.value = 'alert-success'
    } else {
      alertMessage.value = `✕ Test failed for '${ch.name}': ${data?.message || 'Unknown error'}`
      alertType.value = 'alert-error'
    }
    await fetchAlertLogs()
  } catch (err) {
    alertMessage.value = err.response?.data?.detail || 'Failed to trigger test alert.'
    alertType.value = 'alert-error'
  } finally {
    testingChannelId.value = null
  }
}

async function sendModalDiagnosticTest() {
  modalTesting.value = true
  modalTestResult.value = null
  try {
    const testPayload = {
      channel_id: editingChannelId.value || undefined,
      channel_type: channelForm.channel_type,
      name: channelForm.name || 'Draft Diagnostic Channel',
      config: { ...channelForm.config },
    }

    if (channelForm.channel_type === 'GENERIC_WEBHOOK' && channelForm.headersRaw.trim()) {
      try {
        testPayload.config.headers = JSON.parse(channelForm.headersRaw)
      } catch (e) {}
    }

    if (channelForm.channel_type === 'EMAIL_SMTP' && channelForm.toEmailsRaw.trim()) {
      testPayload.config.to_emails = channelForm.toEmailsRaw
        .split(',')
        .map(e => e.trim())
        .filter(Boolean)
    }

    const res = await testAlertChannel(testPayload)
    const data = res.data?.data
    if (data?.success) {
      modalTestResult.value = {
        success: true,
        message: `✓ Success (HTTP ${data.status_code}): Diagnostic alert delivered to ${formatProviderName(channelForm.channel_type)}.`,
      }
    } else {
      modalTestResult.value = {
        success: false,
        message: `✕ Failed: ${data?.message || 'Provider connection rejected.'}`,
      }
    }
    await fetchAlertLogs()
  } catch (err) {
    modalTestResult.value = {
      success: false,
      message: `✕ Test failed: ${err.response?.data?.detail || err.message}`,
    }
  } finally {
    modalTesting.value = false
  }
}

function openAddUserModal() {
  userForm.username = ''
  userForm.password = ''
  userForm.role = 'VIEWER'
  showAddModal.value = true
}

async function saveNewUser() {
  userSaving.value = true
  try {
    await createUser(userForm)
    showAddModal.value = false
    alertMessage.value = `User account '${userForm.username}' created successfully.`
    alertType.value = 'alert-success'
    await fetchUsersList()
  } catch (err) {
    alertMessage.value = err.response?.data?.detail || 'Failed to create user.'
    alertType.value = 'alert-error'
  } finally {
    userSaving.value = false
  }
}

function openResetPasswordModal(user) {
  targetUser.value = user
  resetPasswordVal.value = ''
  showResetModal.value = true
}

async function executeResetPassword() {
  if (!targetUser.value) return
  userSaving.value = true
  try {
    const payload = resetPasswordVal.value ? { password: resetPasswordVal.value } : {}
    await resetUserPassword(targetUser.value.id, payload)
    showResetModal.value = false
    alertMessage.value = `Password for '${targetUser.value.username}' reset successfully.`
    alertType.value = 'alert-success'
    await fetchUsersList()
  } catch (err) {
    alertMessage.value = err.response?.data?.detail || 'Failed to reset password.'
    alertType.value = 'alert-error'
  } finally {
    userSaving.value = false
  }
}

async function toggleUserStatus(user) {
  const newStatus = !user.is_active
  try {
    await updateUser(user.id, { is_active: newStatus })
    alertMessage.value = `User '${user.username}' is now ${newStatus ? 'active' : 'disabled'}.`
    alertType.value = 'alert-success'
    await fetchUsersList()
  } catch (err) {
    alertMessage.value = err.response?.data?.detail || 'Failed to update user status.'
    alertType.value = 'alert-error'
  }
}

async function confirmDeleteUser(user) {
  if (!confirm(`Permanently revoke and delete user account '${user.username}'?`)) return
  try {
    await deleteUser(user.id)
    alertMessage.value = `User '${user.username}' has been removed.`
    alertType.value = 'alert-success'
    await fetchUsersList()
  } catch (err) {
    alertMessage.value = err.response?.data?.detail || 'Failed to delete user.'
    alertType.value = 'alert-error'
  }
}

onMounted(() => {
  loadUserFromStorage()
  loadSettings()
  fetchChannels()
  fetchAlertLogs()
  fetchEndpointsList()
  fetchUsersList()
})
</script>

<style scoped>
.settings-view {
  padding: 24px 32px;
  max-width: 1440px;
  margin: 0 auto;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 4px 0;
}

.page-sub {
  font-size: 13px;
  color: var(--text-muted);
  margin: 0;
}

/* 4-Tab Navigation Strip */
.settings-tabs-nav {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 24px;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.tab-btn:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.02);
}

.tab-btn.active {
  color: var(--color-primary, #3b82f6);
  border-bottom-color: var(--color-primary, #3b82f6);
}

.tab-count {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 10px;
  background: var(--bg-surface-selected);
  color: var(--text-primary);
  font-weight: 700;
}

.tab-pane {
  animation: fadeIn 0.15s ease-in-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

@media (max-width: 1024px) {
  .settings-grid { grid-template-columns: 1fr; }
}

.settings-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: var(--radius, 8px);
  padding: 20px;
}

.full-width {
  grid-column: 1 / -1;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.card-desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
  margin: 0;
}

.setting-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 0;
  border-bottom: 1px solid var(--border-color);
}

.setting-row:last-child {
  border-bottom: none;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
  display: block;
}

.setting-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
}

.label-hint {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: normal;
  margin-left: 6px;
}

/* Engine badge */
.engine-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
}

.badge-redis { background: rgba(239, 68, 68, 0.15); color: #EF4444; border: 1px solid rgba(239, 68, 68, 0.3); }
.badge-pg { background: rgba(59, 130, 246, 0.15); color: #60A5FA; border: 1px solid rgba(59, 130, 246, 0.3); }

/* Provider pills */
.provider-pill {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-surface-selected);
  border: 1px solid var(--border-color);
}
.provider-pill.teams { color: #6264A7; border-color: rgba(98, 100, 167, 0.3); }
.provider-pill.discord { color: #5865F2; border-color: rgba(88, 101, 242, 0.3); }
.provider-pill.slack { color: #ECB22E; border-color: rgba(236, 178, 46, 0.3); }
.provider-pill.email_smtp { color: #10B981; border-color: rgba(16, 185, 129, 0.3); }
.provider-pill.generic_webhook { color: #3B82F6; border-color: rgba(59, 130, 246, 0.3); }

/* Scope badge */
.badge-scope {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--bg-surface-selected);
  color: var(--text-secondary);
}

.badge-scope.all { color: var(--color-primary, #3b82f6); font-weight: 600; }

/* Severities */
.severity-tag-group {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.severity-tag {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--bg-surface-selected);
}
.severity-tag.down { color: #EF4444; background: rgba(239, 68, 68, 0.1); }
.severity-tag.recovered { color: #10B981; background: rgba(16, 185, 129, 0.1); }
.severity-tag.unstable { color: #F59E0B; background: rgba(245, 158, 11, 0.1); }

/* Switch style */
.switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}
.switch input { opacity: 0; width: 0; height: 0; }
.slider {
  position: absolute; cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: var(--border-color);
  transition: .2s;
  border-radius: 24px;
}
.slider:before {
  position: absolute; content: "";
  height: 18px; width: 18px;
  left: 3px; bottom: 3px;
  background-color: white;
  transition: .2s;
  border-radius: 50%;
}
input:checked + .slider { background-color: var(--color-primary, #3b82f6); }
input:checked + .slider:before { transform: translateX(20px); }

/* Driver toggle */
.driver-toggle {
  display: flex;
  background: var(--bg-surface-selected);
  padding: 3px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
}
.btn-toggle-option {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-toggle-option.active {
  background: var(--bg-surface);
  color: var(--text-primary);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.form-select, .form-input {
  background: var(--bg-surface-selected);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  width: 100%;
  box-sizing: border-box;
}

.form-select {
  width: auto;
  min-width: 180px;
}

.truncate-cell {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Modals */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: 16px;
}

.modal-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  width: 100%;
  max-width: 480px;
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.5);
}

.channel-modal-dialog {
  max-width: 800px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.modal-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.modal-subtitle {
  margin: 2px 0 0 0;
  font-size: 12px;
  color: var(--text-muted);
}

.modal-form {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-row-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

/* Provider selector cards */
.provider-selector-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 8px;
}

.provider-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px 8px;
  background: var(--bg-surface-selected);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s;
}

.provider-card:hover {
  border-color: var(--color-primary, #3b82f6);
}

.provider-card.active {
  border-color: var(--color-primary, #3b82f6);
  background: rgba(59, 130, 246, 0.08);
}

.provider-icon { font-size: 20px; }
.provider-name { font-size: 11px; font-weight: 700; color: var(--text-primary); }
.provider-badge { font-size: 9px; color: var(--text-muted); }

/* Target picker in modal */
.target-picker-box {
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--bg-surface-selected);
  padding: 8px;
}

.target-picker-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  gap: 8px;
}

.target-search-input {
  flex: 1;
  background: var(--bg-surface);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 12px;
  padding: 4px 8px;
}

.target-list {
  max-height: 140px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.target-item {
  padding: 4px 6px;
  border-radius: 4px;
}
.target-item:hover { background: var(--bg-surface); }

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-primary);
  cursor: pointer;
}

.radio-options {
  display: flex;
  gap: 16px;
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-primary);
  cursor: pointer;
}

.severity-checkbox-group {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.diagnostic-test-section {
  padding: 12px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.test-feedback-banner {
  font-size: 12px;
  padding: 8px 12px;
  border-radius: 4px;
  font-weight: 500;
}
.test-feedback-banner.success {
  background: rgba(16, 185, 129, 0.1);
  color: #10B981;
  border: 1px solid rgba(16, 185, 129, 0.3);
}
.test-feedback-banner.error {
  background: rgba(239, 68, 68, 0.1);
  color: #EF4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.btn-primary {
  background: var(--color-primary, #3b82f6);
  color: #ffffff;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-secondary {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-secondary:hover { background: var(--bg-surface-selected); color: var(--text-primary); }

.btn-small { padding: 5px 10px; font-size: 12px; }

.btn-action {
  background: transparent;
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s;
}
.btn-action:hover:not(:disabled) { background: var(--bg-surface-hover); color: var(--text-primary); }
.btn-action:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-text-action {
  background: transparent;
  border: none;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-primary, #3b82f6);
  cursor: pointer;
  padding: 0;
}

.btn-close {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
}

.alert-banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 13px;
  margin-bottom: 16px;
}
.alert-success { background: rgba(16, 185, 129, 0.1); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.3); }
.alert-error { background: rgba(239, 68, 68, 0.1); color: #EF4444; border: 1px solid rgba(239, 68, 68, 0.3); }

.role-badge {
  font-size: 11px; font-weight: 700;
  padding: 2px 6px; border-radius: 4px;
}
.role-badge.admin { background: rgba(59, 130, 246, 0.15); color: #60A5FA; }
.role-badge.viewer { background: rgba(107, 114, 128, 0.15); color: #9CA3AF; }

.status-pill {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
}
.status-up { background: rgba(16, 185, 129, 0.15); color: #10B981; }
.status-down { background: rgba(239, 68, 68, 0.15); color: #EF4444; }
.status-unstable { background: rgba(245, 158, 11, 0.15); color: #F59E0B; }

.table-actions { display: flex; justify-content: flex-end; gap: 6px; }
.flex-row-center { display: flex; align-items: center; }
.flex-1 { flex: 1; }
.gap-2 { gap: 8px; }
.mb-4 { margin-bottom: 16px; }
.mt-1 { margin-top: 4px; }
.font-mono { font-family: var(--font-mono); }
.font-bold { font-weight: 600; }
.text-right { text-align: right; }
.text-center { text-align: center; }
.text-xs { font-size: 11px; }
.text-muted { color: var(--text-muted); }
.text-down { color: #EF4444; }
.text-unstable { color: #F59E0B; }
.text-up { color: #10B981; }
.py-6 { padding-top: 24px; padding-bottom: 24px; }
.tnum { font-feature-settings: "tnum"; font-variant-numeric: tabular-nums; }
</style>
