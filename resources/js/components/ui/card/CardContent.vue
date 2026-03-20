<script setup lang="js">
import { cn } from "@/lib/utils"

const props = defineProps({
  class: { default: undefined },
})
</script>

<template>
  <div
    data-slot="card-content"
    :class="cn('px-6', props.class)"
  >
    <slot />
  </div>
</template>
