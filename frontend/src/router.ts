import { createRouter, createWebHistory } from 'vue-router'
import { auth, restoreSession } from './state/auth'
import { homePath, isStaff } from './types'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./pages/PortalGatePage.vue') },
    { path: '/shop/login', component: () => import('./pages/ShopLoginPage.vue'), meta: { guest: true, portal: 'shop' } },
    { path: '/staff/login', component: () => import('./pages/StaffLoginPage.vue'), meta: { guest: true, portal: 'staff' } },
    {
      path: '/shop',
      component: () => import('./layouts/ShopLayout.vue'),
      meta: { portal: 'shop', roles: ['user'] },
      children: [
        { path: '', name: 'support', component: () => import('./pages/SupportPage.vue') },
        { path: 'orders', name: 'shop-orders', component: () => import('./pages/ShopOrdersPage.vue') },
        { path: 'tickets/:id', component: () => import('./pages/TicketPage.vue'), meta: { ticketPortal: 'shop' } },
      ],
    },
    {
      path: '/staff',
      component: () => import('./layouts/StaffLayout.vue'),
      meta: { portal: 'staff', roles: ['agent', 'admin'] },
      children: [
        { path: '', redirect: '/staff/tickets' },
        { path: 'tickets', component: () => import('./pages/TicketsPage.vue') },
        { path: 'tickets/:id', component: () => import('./pages/TicketPage.vue'), meta: { ticketPortal: 'staff' } },
        { path: 'admin/:section(stats|users|groups|categories|faqs)?', component: () => import('./pages/AdminPage.vue'), meta: { admin: true } },
      ],
    },
    // legacy redirects
    { path: '/login', redirect: '/' },
    { path: '/support', redirect: '/shop' },
    { path: '/tickets', redirect: () => (auth.user?.role === 'user' ? '/shop/orders' : '/staff/tickets') },
    { path: '/tickets/new', redirect: '/shop' },
    { path: '/tickets/:id', redirect: (to) => (auth.user?.role === 'user' ? `/shop/tickets/${to.params.id}` : `/staff/tickets/${to.params.id}`) },
    { path: '/faq', redirect: () => homePath(auth.user?.role) },
    { path: '/admin/:section?', redirect: (to) => `/staff/admin/${to.params.section || 'stats'}` },
    { path: '/:pathMatch(.*)*', redirect: () => homePath(auth.user?.role) },
  ],
})

router.beforeEach(async (to) => {
  if (!auth.ready) await restoreSession()
  const roles = to.matched.flatMap((record) => (record.meta.roles as string[] | undefined) || [])
  const needsAuth = to.matched.some((record) => record.meta.portal && !record.meta.guest)

  if (!auth.user) {
    if (to.meta.guest || to.path === '/') return true
    if (to.path.startsWith('/staff')) return '/staff/login'
    if (to.path.startsWith('/shop')) return '/shop/login'
    return '/'
  }

  if (to.meta.guest || to.path === '/') return homePath(auth.user.role)

  if (to.meta.admin && auth.user.role !== 'admin') return '/staff/tickets'

  if (roles.length && !roles.includes(auth.user.role)) {
    return homePath(auth.user.role)
  }

  if (needsAuth && to.meta.portal === 'shop' && auth.user.role !== 'user') return '/staff/tickets'
  if (needsAuth && to.meta.portal === 'staff' && !isStaff(auth.user.role)) return '/shop'

  return true
})
