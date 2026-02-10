import { create } from 'zustand'
import type { Task } from '../types/task'

interface BoardState {
  tasks: Task[]
  selectedTask: Task | null
  setTasks: (tasks: Task[]) => void
  setSelectedTask: (task: Task | null) => void
  updateTask: (task: Task) => void
}

export const useBoardStore = create<BoardState>((set) => ({
  tasks: [],
  selectedTask: null,
  setTasks: (tasks) => set({ tasks }),
  setSelectedTask: (task) => set({ selectedTask: task }),
  updateTask: (updated) =>
    set((state) => ({
      tasks: state.tasks.map((t) => (t.id === updated.id ? updated : t)),
    })),
}))
