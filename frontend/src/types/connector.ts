export interface GDriveConnector {
  id: string
  name: string
  folder_id?: string
  status: 'idle' | 'syncing' | 'error' | 'disconnected'
  files_synced: number
  last_sync_at?: string
}

export interface M365Connector {
  id: string
  name: string
  status: 'idle' | 'syncing' | 'error' | 'disconnected'
  files_synced: number
  last_sync_at?: string
}

export interface SyncProgress {
  total: number
  synced: number
  skipped: number
  failed?: number
  percent: number
  status: string
}

export type SourceKey = 'uploaded' | 'gdrive' | 'localfs' | 'teams' | 'sharepoint' | 'onedrive'

export interface SourceConfig {
  label: string
  color: string
  bg: string
  border: string
}
