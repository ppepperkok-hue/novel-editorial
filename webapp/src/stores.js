import { create } from "zustand";
import { getControl, getDashboard } from "./api.js";

export const usePipelineStore = create((set) => ({
  data: null,
  control: null,
  liveSnapshot: null,
  fetchDashboard: async () => {
    set({ data: await getDashboard() });
  },
  fetchControl: async () => {
    set({ control: await getControl() });
  },
  setLiveSnapshot: (snapshot) => set({ liveSnapshot: snapshot }),
}));
