<script setup lang="js">
import { cn } from "@/lib/utils"
import { Separator } from '@/components/ui/separator'

const props = defineProps({
  class: { default: undefined },
})
</script>

<template>
  <Separator
    data-slot="sidebar-separator"
    data-sidebar="separator"
    :class="cn('bg-sidebar-border mx-2 w-auto', props.class)"
  >
    <slot />
  </Separator>
</template>
