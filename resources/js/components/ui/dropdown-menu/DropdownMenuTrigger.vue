<script setup lang="js">
import { DropdownMenuTrigger, useForwardProps } from "reka-ui"

const props = defineProps({
  disabled: { type: Boolean, default: false },
  as: { default: undefined },
  asChild: { type: Boolean, default: false },
})

const forwardedProps = useForwardProps(props)
</script>

<template>
  <DropdownMenuTrigger
    data-slot="dropdown-menu-trigger"
    v-bind="forwardedProps"
  >
    <slot />
  </DropdownMenuTrigger>
</template>
