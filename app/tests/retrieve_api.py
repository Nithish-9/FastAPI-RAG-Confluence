import asyncio
import httpx
import time

URL = "https://pleasant-whippet-select.ngrok-free.app/rag/retrieve"

TEST_QUERIES = [
    "Where did scientists find Steve Rogers in the present day?",
    "In what year did Johann Schmidt steal the Tesseract from Norway?",
    "Why was Steve Rogers initially rejected for U.S. Army recruitment?",
    "Who is the famous engineer that held the Stark Expo in the 1940s?",
    "What was the name of the super-soldier experiment Rogers joined?",
    "Which British MI6 agent helped oversee the super-soldier project?",
    "What selfless act convinced Colonel Phillips that Rogers was the right candidate?",
    "What happened to Johann Schmidt when he took the prototype serum?",
    "Who was the scientist that created the successful super-soldier formula?",
    "What specific rays were used to dose Rogers during his transformation?",
    "Who killed Dr. Abraham Erskine?",
    "What was Steve Rogers’ primary role immediately after the experiment?",
    "Which unit was Bucky Barnes part of before being captured by Hydra?",
    "What metal is Captain America’s circular shield made of?",
    "What is the name of the elite unit Rogers recruits to fight Hydra?",
    "How did Bucky Barnes supposedly die during the mission on the train?",
    "What happens to the Red Skull when he touches the Tesseract?",
    "Where did Captain America crash his plane at the end of the war?",
    "How many years was Steve Rogers asleep before being found?",
    "Who is the director of S.H.I.E.L.D. who greets Rogers in Times Square?",
    "In which country was Tony Stark ambushed by the Ten Rings?",
    "What is the name of the doctor who saved Tony’s life in the cave?",
    "What device was implanted in Tony’s chest to keep shrapnel from his heart?",
    "What did the Ten Rings want Tony to build in exchange for his freedom?",
    "What was the name of the first prototype armor built in the cave?",
    "Who was Tony Stark's military liaison and best friend?",
    "What major announcement did Tony make upon his return from captivity?",
    "Who was Howard Stark’s old partner and the manager of Stark Industries?",
    "What gift did Pepper Potts give Tony involving his original arc reactor?",
    "Who is the reporter that told Tony his weapons were being used by terrorists?",
    "How did the Air Force discover Iron Man’s secret identity during a dogfight?",
    "What happened to the leader of the Ten Rings, Raza?",
    "What was the name of the massive suit built by Obadiah Stane?",
    "Why couldn't Stane’s scientists build a miniaturized arc reactor?",
    "How did Stane paralyze Tony Stark before stealing his heart piece?",
    "Which S.H.I.E.L.D. agent did Pepper Potts meet to report Stane?",
    "Where did the final battle between Iron Man and Iron Monger take place?",
    "How did Tony Stark kill Obadiah Stane?",
    "What did Tony Stark say at the press conference at the end of the movie?",
    "What initiative did Nick Fury want to discuss in the post-credits scene?",
    "Who is the Russian scientist seeking revenge on the Stark family?",
    "Why did Ivan Vanko blame Howard Stark for his father's death?",
    "What is the name of Tony’s business rival who helped Vanko?",
    "What element in the arc reactor was slowly poisoning Tony Stark?",
    "Whom did Tony appoint as the new CEO of Stark Industries?",
    "What was Black Widow’s alias when she was first hired by Tony?",
    "During which race in Monaco did Vanko attack Tony Stark?",
    "What weapon does Ivan Vanko use to fight Iron Man?",
    "Why did James Rhodes steal the Mark II prototype suit?",
    "Who was one of the original founders of S.H.I.E.L.D. alongside Nick Fury?",
    "What did Tony find hidden in the diorama of the 1974 Stark Expo?",
    "How did Tony Stark synthesize the new element for his heart?",
    "What was the re-branded name of the suit James Rhodes wore?",
    "Who took remote control of the Hammer Drones during the Expo?",
    "Where did Black Widow and Happy Hogan go to stop Vanko?",
    "How did Ivan Vanko die at the end of the film?",
    "What role did S.H.I.E.L.D. offer Tony at the end of the debriefing?",
    "What object was found in New Mexico during the post-credits scene?",
    "Who discovered Thor’s hammer in the desert?",
    "What AI assistant helps Tony determine the structure of the new element?",
    "Where did Tony Stark first meet Maya Hansen in 1999?",
    "What is the name of the regenerative treatment invented by Hansen?",
    "Who is the disabled scientist who founded A.I.M.?",
    "What psychological condition is Tony suffering from after New York?",
    "What happened to Happy Hogan during the bombing at the Chinese Theater?",
    "Why did the Mandarin send helicopters to destroy Tony’s Malibu home?",
    "In which state did J.A.R.V.I.S. land Tony after the house attack?",
    "Who is the young boy that helps Tony repair his suit in Tennessee?",
    "What was the real cause of the Mandarin bombings?",
    "Who was the real mastermind behind the Mandarin terrorist persona?",
    "What was the true identity of the actor Trevor Slattery?",
    "What was the re-branded name for War Machine in Iron Man 3?",
    "Why did Killian inject Pepper Potts with Extremis?",
    "How did Maya Hansen die?",
    "Which official was kidnapped and placed inside the Iron Patriot armor?",
    "What was the name of the protocol Tony used to summon all his suits?",
    "How did Pepper Potts survive her fall into the fire?",
    "Who ultimately killed Aldrich Killian?",
    "What happened to the Vice President at the end of the film?",
    "What did Tony do with his arc reactor at the end of the movie?",
    "Which university did Bruce Banner work at during the accident?",
    "Who is the General obsessed with capturing the Hulk?",
    "What heart rate triggers Bruce Banner’s transformation?",
    "Where was Bruce Banner hiding while working at a bottling factory?",
    "How did the military track Banner to South America?",
    "Who is the soldier that volunteered to be injected with the serum?",
    "What is the internet alias of the scientist Samuel Sterns?",
    "Who is Bruce Banner’s love interest and Ross's daughter?",
    "What creature did Emil Blonsky turn into after taking Banner's blood?",
    "In which New York neighborhood did the Hulk fight the Abomination?",
    "What happened to Samuel Sterns after he was attacked by Blonsky?",
    "Why did the Hulk spare the Abomination's life?",
    "Where was Banner practicing controlled transformations a month later?",
    "Who approached General Ross at a bar in the final scene?",
    "Who is the king of Asgard and father to Thor and Loki?",
    "Why was Thor exiled to Earth by his father?",
    "Who are the two Maximoff twins introduced in Sokovia?",
    "What is the name of the sentient AI that tried to eradicate humanity?",
    "What powerful gem was hidden inside Loki’s scepter?",
    "Which character is created by uploading J.A.R.V.I.S. into a synthetic body?"
]

async def make_request(client, i, query):
    payload = {
        "query": query,
        "top_k": 5,
        "alpha": 0.75,
        "page_id": None,
        "chunk_index": None
    }
    start = time.perf_counter()
    try:
        resp = await client.post(URL, json=payload, timeout=30.0)
        end = time.perf_counter()
        print(f"Req {i} | Query: {query} | Status: {resp.status_code} | Time: {end - start:.2f}s")
    except Exception as e:
        print(f"Req {i} failed: {e}")

async def main():
    async with httpx.AsyncClient() as client:
        tasks = [make_request(client, i, TEST_QUERIES[i]) for i in range(len(TEST_QUERIES))]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())