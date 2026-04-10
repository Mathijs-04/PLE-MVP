# Warhammer Rule Assistant

## Project Summary
Warhammer Rule Assistant is a question-answering tool for tabletop Warhammer rules. It answers rule-related questions using official rule sources.

## Tech Summary
- **Backend:** Laravel API endpoint (`/api/chat`) receives user questions.
- **AI Service:** Python FastAPI endpoint (`/ask`) processes questions using AI and returns answers.
- **Frontend:** Laravel + Vite + Vue provides the chat interface.
- **Flow:** User asks a question in the UI -> Laravel forwards it to Python -> Python uses AI and returns an answer -> Laravel sends it back to the UI.

## Data Summary
- **Core Rules:** Official Warhammer PDF rule documents are used as primary rule references.
- **Faction Rules:** The GitHub BSData repository is used for faction-specific rule data.
