@tool
extends Node
class_name MyClass

const Foo = preload("res://foo.gd")
const Bar = load("res://bar.gd")

signal hit(damage: int)
signal died

enum State { IDLE, RUN = 2, JUMP }
enum { ANON_A, ANON_B }

@export var health: int = 100
@export_range(0, 200) var speed: float = 5.0
@onready var sprite = null

var score: int :
    get:
        return score
    set(value):
        score = value

var legacy: int setget set_legacy, get_legacy

class Inner extends Resource:
    func helper() -> void:
        pass

func _ready() -> void:
    var add_fn = func(a, b): return a + b
    var shout = func loud(msg): print(msg)
    var x = Foo.new()
    helper()
    emit_signal("hit", 3)
    hit.emit(5)
    died.emit()

static func util() -> int:
    return 1

func set_legacy(v): pass
func get_legacy(): return 0
