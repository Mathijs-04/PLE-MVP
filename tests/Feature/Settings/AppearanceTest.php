<?php

use App\Models\User;
use Inertia\Testing\AssertableInertia as Assert;

test('appearance page is displayed', function () {
    $user = User::factory()->create();

    $this->actingAs($user)
        ->get(route('appearance.edit'))
        ->assertOk()
        ->assertInertia(fn (Assert $page) => $page
            ->component('settings/Appearance'),
        );
});
