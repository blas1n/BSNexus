import { create } from 'zustand'
import type { DesignSession } from '../types/architect'

interface ArchitectState {
  currentSession: DesignSession | null
  isLoading: boolean
  setCurrentSession: (session: DesignSession | null) => void
  setLoading: (loading: boolean) => void
}

export const useArchitectStore = create<ArchitectState>((set) => ({
  currentSession: null,
  isLoading: false,
  setCurrentSession: (session) => set({ currentSession: session }),
  setLoading: (loading) => set({ isLoading: loading }),
}))
