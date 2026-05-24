<?php

use App\Services\AiService;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

uses(TestCase::class);

beforeEach(function () {
    config(['services.ai.url' => 'http://fake-ai.test']);
});

test('returns decoded json on successful response', function () {
    Http::fake([
        'fake-ai.test/ask' => Http::response([
            'short_answer' => 'Yes.',
            'detailed_answer' => 'Details here.',
            'source' => 'Core Rules',
            'certainty' => 2,
        ], 200),
    ]);

    $result = app(AiService::class)->ask('Can I move?', 'aos');

    expect($result)->toBe([
        'short_answer' => 'Yes.',
        'detailed_answer' => 'Details here.',
        'source' => 'Core Rules',
        'certainty' => 2,
    ]);
});

test('returns error envelope on failed response', function () {
    Http::fake([
        'fake-ai.test/ask' => Http::response('Bad gateway', 502),
    ]);

    $result = app(AiService::class)->ask('Can I move?', 'aos');

    expect($result)->toMatchArray([
        'error' => 'AI service request failed',
        'status' => 502,
        'body' => 'Bad gateway',
    ]);
});

test('normalizes 40k to wh40k in outbound request', function () {
    Http::fake([
        'fake-ai.test/ask' => Http::response(['short_answer' => 'Yes.'], 200),
    ]);

    app(AiService::class)->ask('Can I move?', '40K');

    Http::assertSent(function ($request) {
        return $request->url() === 'http://fake-ai.test/ask'
            && $request['game'] === 'wh40k';
    });
});

test('posts to configured base url with ask path', function () {
    Http::fake([
        'fake-ai.test/ask' => Http::response(['short_answer' => 'Yes.'], 200),
    ]);

    app(AiService::class)->ask('Can I move?', 'aos');

    Http::assertSent(function ($request) {
        return $request->url() === 'http://fake-ai.test/ask'
            && $request['question'] === 'Can I move?'
            && $request['game'] === 'aos';
    });
});
