<?php

test('health endpoint returns successful response', function () {
    $response = $this->get('/up');

    $response->assertSuccessful();
});
