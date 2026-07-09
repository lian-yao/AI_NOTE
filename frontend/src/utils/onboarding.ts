export const ONBOARDING_STORAGE_KEY = 'ai-video-onboarded'
export const ONBOARDING_VERSION = 'desktop-setup-v2'

export function hasCompletedOnboarding() {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem(ONBOARDING_STORAGE_KEY) === ONBOARDING_VERSION
}

export function markOnboardingComplete() {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(ONBOARDING_STORAGE_KEY, ONBOARDING_VERSION)
}
