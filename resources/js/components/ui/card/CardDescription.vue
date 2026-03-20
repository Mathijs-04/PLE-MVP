<script setup lang="js">
import { cn } from "@/lib/utils"

const props = defineProps({
  class: { default: undefined },
})
</script>

<template>
  <p
    data-slot="card-description"
    :class="cn('text-muted-foreground text-sm', props.class)"
  >
    <slot />
  </p>
</template>
