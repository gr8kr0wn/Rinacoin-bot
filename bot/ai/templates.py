"""Template fallback strings for every prompt_type — no AI dependency."""

import random

TEMPLATES = {
    "daily_greeting": [
        "Purrr... {streak} days in a row! +{points} for you",
        "*Rina rubs against your leg.* Streak: {streak} days!",
        "{points} points added. Rina approves of this routine.",
        "Another day, another {points} points. Rina's watching your streak grow.",
        "Meow! {streak} day streak! Here's {points} points",
        "You get {points} points. Rina headbutts your hand approvingly.",
        "Rina stretches and yawns. Streak: {streak}. Points: +{points}.",
    ],
    "mood_change": [
        "*Rina's mood shifts...* {old_mood} to {new_mood}",
        "Rina flicks her tail. Feeling {new_mood} now.",
        "*Ears twitch.* Rina is feeling {new_mood}.",
        "A soft meow. {new_mood} settles over Rina.",
        "Rina curls up differently. Mood: {new_mood}.",
        "The cat's whiskers quiver. {old_mood} -> {new_mood}.",
    ],
    "referral_reward": [
        "{referrer_name} brought {referred_name} here! +50 points",
        "*Rina weaves between legs.* New friend through {referrer_name}!",
        "New cat in town! Thanks {referrer_name} for bringing {referred_name}",
        "{referrer_name} referred {referred_name}. Good human.",
        "Meow! {referred_name} joined thanks to {referrer_name}",
    ],
    "achievement_unlock": [
        "Meowvelous! Achievement unlocked: {achievement_name}",
        "*Rina does a little dance.* {achievement_name} done!",
        "'{achievement_name}' unlocked. Rina is impressed.",
        "Paws up! Achievement: {achievement_name}",
        "{achievement_name} unlocked! Rina purrs approvingly.",
    ],
    "free_chat": [
        "*Rina cocks her head.* {message}",
        "Rina considers that... *flick flick*",
        "Meow? Is that so.",
        "*Rina blinks slowly.* Tell me more.",
        "*Tail swishes.* Rina heard that.",
        "*A tiny paw reaches out.* Interesting.",
    ],
    "lonely_ping": [
        "*Rina meows at the empty room.* It's been {hours} hours...",
        "Rina is kneading the floor anxiously. Anyone there?",
        "The room is too quiet. Rina's whiskers droop.",
        "A sad meow echoes. {hours} hours alone...",
        "Rina checks the door for the {hours}th time...",
    ],
    "welcome": [
        "Welcome! Rina circles your feet curiously.",
        "*Sniff sniff.* New friend! Rina approves.",
        "Rina welcomes you with a headbutt and a purr.",
        "A new human has joined! Rina is investigating.",
        "Meow! Welcome to the pride.",
        "Rina's tail goes up. A new friend arrived!",
    ],
}


def pick_template(prompt_type: str, **context) -> str:
    templates = TEMPLATES.get(prompt_type)
    if not templates:
        return "Meow."
    template = random.choice(templates)
    for key, value in context.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template
