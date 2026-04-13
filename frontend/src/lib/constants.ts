import { SourceConfig, SourceKey } from '@/types/connector'

export const NAVY = '#060B4E'
export const ORANGE = '#FA9600'
export const BLUE = '#0096D5'

export const SOURCE_CONFIG: Record<SourceKey, SourceConfig> = {
  uploaded:   { label: 'Uploaded Docs', color: '#1E293B', bg: '#F1F5F9', border: '#CBD5E1' },
  gdrive:     { label: 'Google Drive',  color: '#0C447C', bg: '#E6F1FB', border: '#B5D4F4' },
  localfs:    { label: 'Local Files',   color: '#065F46', bg: '#ECFDF5', border: '#6EE7B7' },
  teams:      { label: 'Teams',         color: '#3C3489', bg: '#EEEDFE', border: '#AFA9EC' },
  sharepoint: { label: 'SharePoint',    color: '#712B13', bg: '#FAECE7', border: '#F5C4B3' },
  onedrive:   { label: 'OneDrive',      color: '#085041', bg: '#E1F5EE', border: '#9FE1CB' },
}

export const ALL_SOURCES: SourceKey[] = ['uploaded', 'gdrive', 'localfs', 'teams', 'sharepoint', 'onedrive']

export const ROLE_COLORS: Record<string, string> = {
  admin: '#F59E0B',
  user: '#10B981',
  viewer: '#94A3B8',
}

export const AUTH_KEY = 'intellirag_auth'
export const SESSION_KEY = (tenant: string) => `intellirag_session_${tenant}`
