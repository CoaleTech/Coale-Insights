<!--
  Loading placeholder shaped like the content it replaces.

  frappe-ui 0.1.142 ships no Skeleton component (Spinner and LoadingIndicator
  only), so this is the local stand-in. Caller sets the dimensions:

    <SkeletonBlock class="h-7 w-28" />

  Respects prefers-reduced-motion: the pulse is dropped, the placeholder stays.
-->
<template>
  <div class="skeleton-block rounded bg-surface-gray-2" aria-hidden="true" />
</template>

<style scoped>
.skeleton-block {
	animation: skeleton-pulse 1.6s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes skeleton-pulse {
	50% {
		opacity: 0.45;
	}
}

@media (prefers-reduced-motion: reduce) {
	.skeleton-block {
		animation: none;
	}
}
</style>
