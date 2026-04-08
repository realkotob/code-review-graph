extends Node

onready var sprite = null
onready var hud = null

var score setget set_score, get_score

remote func networked_action():
    pass

master func master_only():
    pass

puppet func puppet_only():
    pass

remotesync func everyone():
    pass

func set_score(v):
    score = v

func get_score():
    return score

func _ready():
    set_process(true)
