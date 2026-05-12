<script setup lang="js">
defineProps({
    modelValue: {
        type: String,
        required: true,
    },
    disabled: {
        type: Boolean,
        default: false,
    },
    name: {
        type: String,
        default: 'game',
    },
});

const emit = defineEmits(['update:modelValue']);

const gameOptions = [
    {
        value: 'aos',
        label: 'Warhammer Age of Sigmar',
        shortLabel: 'AOS',
    },
    {
        value: '40k',
        label: 'Warhammer 40.000',
        shortLabel: '40K',
    },
];

function selectGame(value) {
    emit('update:modelValue', value);
}
</script>

<template>
    <fieldset class="min-w-0">
        <legend class="sr-only">Game system</legend>
        <div class="flex flex-row items-center gap-5">
            <label
                v-for="option in gameOptions"
                :key="option.value"
                class="flex cursor-pointer items-center gap-2 text-sm transition-colors focus-within:outline-none"
                :class="[
                    modelValue === option.value
                        ? 'font-semibold text-foreground'
                        : 'text-muted-foreground hover:text-foreground',
                    disabled ? 'cursor-not-allowed opacity-50' : '',
                ]"
            >
                <input
                    :name="name"
                    type="radio"
                    class="peer sr-only"
                    :value="option.value"
                    :checked="modelValue === option.value"
                    :disabled="disabled"
                    @change="selectGame(option.value)"
                />
                <span
                    aria-hidden="true"
                    class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 bg-transparent transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2"
                    :class="
                        modelValue === option.value
                            ? 'border-foreground'
                            : 'border-muted-foreground dark:border-foreground/80'
                    "
                >
                    <span
                        class="h-2 w-2 rounded-full bg-foreground transition-opacity"
                        :class="
                            modelValue === option.value
                                ? 'opacity-100'
                                : 'opacity-0'
                        "
                    />
                </span>
                <span>
                    <span class="sm:hidden">{{ option.shortLabel }}</span>
                    <span class="hidden sm:inline">{{ option.label }}</span>
                </span>
            </label>
        </div>
    </fieldset>
</template>
