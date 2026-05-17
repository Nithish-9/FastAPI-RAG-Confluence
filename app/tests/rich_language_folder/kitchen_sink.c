#ifndef TREE_SITTER_STRESS_TEST_H
#define TREE_SITTER_STRESS_TEST_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

/* 1. Preprocessor Macros (Function-like, Token Concatenation, and Variadic) */
#define MAX_BUFFER_SIZE 1024
#define REPEAT_CMD(cmd, x) cmd ## x
#define LOG_ERROR(fmt, ...) fprintf(stderr, "[ERROR] " fmt "\n", __VA_ARGS__)

/* 2. Global Enums, Typedefs, and Forward Declarations */
typedef uint32_t flags_t;

enum EngineStatus {
    STATUS_IDLE = 0,
    STATUS_RUNNING,
    STATUS_ERROR = -1
};

// Forward declarations
struct Node;
typedef struct Node Node_t;

/* 3. Complex Structs (Nested, Bit-fields, and Function Pointers) */
struct Node {
    int id;
    char name[32];
    void *data;
    Node_t *next;
    
    // Bit-fields for packed allocation flags
    flags_t is_active : 1;
    flags_t permission : 3;
    flags_t reserved : 4;

    // Function pointer inside a struct
    int (*callback)(int, const char*);
};

/* 4. Global and Static Variables (Storage Class Specifiers) */
static const double PI = 3.14159265358979323846;
extern int global_system_entropy;
volatile int hardware_register = 0x00;

/* 5. Compound Literals & Variadic Functions */
static void process_coordinates(int coords[2]) {
    printf("X: %d, Y: %d\n", coords[0], coords[1]);
}

double calculate_sum(int count, ...) {
    double sum = 0.0;
    __builtin_va_list args;
    __builtin_va_start(args, count);
    for (int i = 0; i < count; i++) {
        sum += __builtin_va_arg(args, double);
    }
    __builtin_va_end(args);
    return sum;
}

/* 6. Main Stress-Test Function Execution */
int main(int argc, char *argv[]) {
    // Basic initializations
    int status_code = STATUS_IDLE;
    char *buffer = (char *)malloc(MAX_BUFFER_SIZE * sizeof(char));
    
    if (buffer == NULL) {
        LOG_ERROR("Memory allocation failed for size: %d", MAX_BUFFER_SIZE);
        return STATUS_ERROR;
    }

    // 7. Compound Literal Assignment
    process_coordinates((int[]){10, 20});

    // 8. Dynamic Struct Stack Construction & Arrow Operator Reference
    Node_t head = {
        .id = 1,
        .name = "RootNode",
        .data = NULL,
        .next = NULL,
        .is_active = 1,
        .permission = 5,
        .callback = NULL
    };

    Node_t *current = &head;

    // 9. Complex Control Flow: Switch Statements with Fallthrough
    switch (argc) {
        case 1:
            printf("No arguments passed.\n");
            // Intentional fallthrough
        case 2:
            if (argv[1] != NULL && strcmp(argv[1], "--debug") == 0) {
                status_code = STATUS_RUNNING;
            }
            break;
        default:
            printf("Multiple arguments parsed.\n");
            break;
    }

    // 10. Loops, Pointer Arithmetic, and Multi-dimensional Arrays
    int matrix[2][3] = {{1, 2, 3}, {4, 5, 6}};
    int (*matrix_ptr)[3] = matrix; // Pointer to an array

    for (int i = 0; i < 2; i++) {
        for (int j = 0; j < 3; j++) {
            // Testing pointer arithmetic equivalence: matrix[i][j]
            int value = *(*(matrix_ptr + i) + j);
            if (value % 2 == 0) {
                continue;
            }
        }
    }

    // 11. Type Casting & Goto Labels (Error handling / cleanup jump)
    void *raw_memory = (void *)&head;
    Node_t *cast_node = (Node_t *)raw_memory;

    if (cast_node->id != 1) {
        goto cleanup;
    }

    // 12. Function Pointer Invocation
    int inline_callback(int code, const char* msg) {
        // GNU C Extension: Nested function support checking
        return code + (msg != NULL ? 1 : 0);
    }
    head.callback = inline_callback;

    if (head.callback != NULL) {
        int result = head.callback(42, "Execute");
    }

cleanup:
    free(buffer);
    return status_code == STATUS_RUNNING ? 0 : 1;
}

#endif /* TREE_SITTER_STRESS_TEST_H */