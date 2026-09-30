#ifndef AEROSIM_EXCLUSIVE_FILE_H
#define AEROSIM_EXCLUSIVE_FILE_H

#include <cstdio>
#include <string>

// Creates a new file exclusively. Opening fails if the destination already exists.
class ExclusiveFile {
public:
    explicit ExclusiveFile(const std::string& path);
    ~ExclusiveFile();

    ExclusiveFile(const ExclusiveFile&) = delete;
    ExclusiveFile& operator=(const ExclusiveFile&) = delete;

    void write(const std::string& contents);
    void close();

private:
    std::FILE* file_ = nullptr;
    std::string path_;
};

#endif // AEROSIM_EXCLUSIVE_FILE_H
