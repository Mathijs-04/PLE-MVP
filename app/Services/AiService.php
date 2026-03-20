<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;

class AiService
{
    public function ask(string $question, string $game): array
    {
        $game = $this->normalizeGame($game);

        $response = Http::timeout(60)->post(
            rtrim(config('services.ai.url'), '/').'/ask',
            [
                'question' => $question,
                'game' => $game,
            ],
        );

        if ($response->failed()) {
            return [
                'error' => 'AI service request failed',
                'status' => $response->status(),
                'body' => $response->body(),
            ];
        }

        return $response->json();
    }

    private function normalizeGame(string $game): string
    {
        $g = strtolower(trim($game));

        if ($g === '40k') {
            return 'wh40k';
        }

        return $g;
    }
}
