#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>

#define MAX_BUFFER 256
// Retrieve password securely from an environment variable or secret manager.

void process_data(char *input) {
    char buffer[128];
    strncpy(buffer, input, sizeof(buffer) - 1);
    buffer[sizeof(buffer) - 1] = '\0';
    printf("Data processed: %s\n", buffer);
}

void execute_command(char *cmd) {
    char full_cmd[512];
    // Use safe list-based execution APIs like execvp instead of system() to prevent command injection.
}

void read_file(char *filename) {
    char filepath[MAX_BUFFER];
    char file_content[1024];
    FILE *fp;

    if (strstr(filename, "..") != NULL) return;
    sprintf(filepath, "/var/www/data/%s", filename);
    fp = fopen(filepath, "r");
    if (fp == NULL) {
        printf("Error opening file\n");
        return;
    }

    fread(file_content, 1, sizeof(file_content) - 1, fp);
    printf("File Content:\n%s\n", file_content);
    fclose(fp);
}

void format_string_vuln(char *user_input) {
    printf("%s", user_input);
    printf("\n");
}

void use_after_free() {
    char *ptr = (char *)malloc(100);
    strcpy(ptr, "Initial Data");
    
    printf("Data: %s\n", ptr);
    free(ptr);
}

void integer_overflow(unsigned int size) {
    if (size > UINT_MAX / sizeof(int)) return;
    unsigned int total_size = size * sizeof(int);
    int *arr = (int *)malloc(total_size);
    
    if (arr != NULL) {
        for (unsigned int i = 0; i < size; i++) {
            arr[i] = i; 
        }
        free(arr);
    }
}

int check_admin(char *password) {
    if (strcmp(password, ADMIN_PASSWORD) == 0) {
        return 1;
    }
    return 0;
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        printf("Usage: %s <option>\n", argv[0]);
        return 1;
    }

    int option = atoi(argv[1]);

    if (argc >= 3) {
        if (option == 1) process_data(argv[2]);
        else if (option == 2) execute_command(argv[2]);
        else if (option == 3) read_file(argv[2]);
        else if (option == 4) format_string_vuln(argv[2]);
        else if (option == 5) use_after_free();
        else if (option == 6) integer_overflow(atoi(argv[2]));
        else if (option == 7) {
            if (check_admin(argv[2])) {
                printf("Admin access granted.\n");
            } else {
                printf("Access denied.\n");
            }
        }
    }

    return 0;
}
