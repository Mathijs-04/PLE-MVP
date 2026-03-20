<script setup lang="js">
import { DropdownMenuGroup } from "reka-ui"

const props = defineProps({
  as: { default: undefined },
  asChild: { type: Boolean, default: false },
})
</script>

<template>
  <DropdownMenuGroup
    data-slot="dropdown-menu-group"
    v-bind="props"
  >
    <slot />
  </DropdownMenuGroup>
</template>
