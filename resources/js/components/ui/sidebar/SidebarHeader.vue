<script setup lang="js">
import { cn } from "@/lib/utils"

const props = defineProps({
  class: { default: undefined },
})
</script>

<template>
  <div
    data-slot="sidebar-header"
    data-sidebar="header"
    :class="cn('flex flex-col gap-2 p-2', props.class)"
  >
    <slot />
  </div>
</template>
