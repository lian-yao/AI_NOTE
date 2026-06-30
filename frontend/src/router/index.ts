import { createRouter, createWebHistory } from "vue-router"

const routes = [
  { path: "/", name: "dashboard", component: () => import("@/views/DashboardView.vue"), meta: { title: "工作台" } },
  { path: "/videos", name: "video-list", component: () => import("@/views/VideoListView.vue"), meta: { title: "视频列表" } },
  { path: "/videos/:videoId", name: "video-detail", component: () => import("@/views/VideoDetailView.vue"), meta: { title: "视频详情" } },
  { path: "/qa", name: "qa", component: () => import("@/views/QAView.vue"), meta: { title: "智能问答" } },
  { path: "/settings", name: "settings", component: () => import("@/views/SettingsView.vue"), meta: { title: "系统设置" } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
